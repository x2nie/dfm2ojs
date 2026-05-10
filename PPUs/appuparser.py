"""
Ringkasan PPU berbasis output ppudump.

Script ini tidak membaca struktur .ppu langsung. Ia menjalankan ppudump lalu
mengekstrak daftar type, class, dan property dengan visibility published.
Parser Python langsung dipisahkan ke bppuparserpy.py sebagai fallback
eksperimental.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


DEFINITION_LABELS = (
    "Enumeration type definition",
    "Array definition",
    "Ordinal definition",
    "Procedural type (ProcVar) definition",
    "Object/Class definition",
    "Record definition",
    "Pointer definition",
    "Set definition",
    "Class reference definition",
    "ShortString definition",
    "AnsiString definition",
    "WideString definition",
    "UnicodeString definition",
    "Longstring definition",
    "Float definition",
    "File definition",
    "Variant definition",
    "Undefined definition",
    "Generic definition",
)


class PPUDumpSummaryParser:
    """Ringkas output ppudump menjadi daftar type, class, dan property published."""

    TYPE_SYM_RE = re.compile(r"Type symbol\s+(.+)$")
    CLASS_RE = re.compile(r"Name of Class\s*:\s*(.+)$")
    PROPERTY_RE = re.compile(r"Property\s+(.+)$")

    def __init__(self, filename: str, ppudump_path: str = "ppudump"):
        self.filename = filename
        self.ppudump_path = ppudump_path
        self.types: List[Dict[str, str]] = []
        self.classes: Dict[str, Dict[str, Any]] = {}
        self._symid_to_type: Dict[str, str] = {}
        self._defid_to_type: Dict[str, str] = {}

    def parse(self):
        cmd = [self.ppudump_path, "-VDS", self.filename]
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode not in (0, 217):
            raise RuntimeError((proc.stderr or proc.stdout).strip())
        self._parse_text(proc.stdout)

    def _parse_text(self, text: str):
        current_def: Optional[Dict[str, str]] = None
        current_class: Optional[str] = None
        current_property: Optional[Dict[str, Any]] = None
        current_symbol: Optional[Dict[str, str]] = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            def_match = re.match(r"\*\* Definition Id (\d+) \*\*", line)
            if def_match:
                current_def = {"id": def_match.group(1), "kind": "", "type_symbol_ref": ""}
                current_property = None
                current_symbol = None
                continue

            if current_def and not current_def["kind"] and line in DEFINITION_LABELS:
                current_def["kind"] = line
                continue

            if line.startswith("Type symbol :") and current_def is not None:
                current_def["type_symbol_ref"] = self._clean_ref(line.split(":", 1)[1])
                continue

            class_match = self.CLASS_RE.search(line)
            if class_match and current_def is not None:
                current_class = class_match.group(1).strip()
                class_info = self.classes.setdefault(
                    current_class,
                    {
                        "name": current_class,
                        "def_id": current_def["id"],
                        "kind": current_def.get("kind", "Object/Class definition"),
                        "ancestor": "",
                        "properties": [],
                    },
                )
                self._defid_to_type[current_def["id"]] = current_class
                sym_id = self._extract_ref_id(current_def.get("type_symbol_ref", ""), "SymId")
                if sym_id:
                    self._symid_to_type[sym_id] = current_class
                continue

            if line.startswith("Ancestor Class :") and current_class:
                self.classes[current_class]["ancestor"] = self._clean_ref(line.split(":", 1)[1])
                continue

            symbol_id_match = re.match(r"\*\* Symbol Id (\d+) \*\*", line)
            if symbol_id_match:
                current_symbol = {"id": symbol_id_match.group(1), "name": "", "visibility": ""}
                current_property = None
                continue

            type_match = self.TYPE_SYM_RE.search(line)
            if type_match and current_symbol is not None:
                current_symbol["name"] = type_match.group(1).strip()
                continue

            if current_symbol and line.startswith("Visibility :"):
                current_symbol["visibility"] = line.split(":", 1)[1].strip()
                if current_property is not None:
                    current_property["visibility"] = current_symbol["visibility"]
                continue

            if current_symbol and current_symbol["name"] and line.startswith("Result Type :"):
                raw_ref = self._clean_ref(line.split(":", 1)[1])
                resolved = self._resolve_ref(raw_ref)
                item = {
                    "name": current_symbol["name"],
                    "sym_id": current_symbol["id"],
                    "visibility": current_symbol.get("visibility", ""),
                    "type": resolved,
                    "raw_ref": raw_ref,
                }
                self.types.append(item)
                self._symid_to_type[current_symbol["id"]] = current_symbol["name"]
                def_id = self._extract_ref_id(raw_ref, "DefId")
                if def_id:
                    self._defid_to_type.setdefault(def_id, current_symbol["name"])
                current_symbol = None
                continue

            property_match = self.PROPERTY_RE.search(line)
            if property_match and current_class:
                current_property = {
                    "name": property_match.group(1).strip(),
                    "visibility": "",
                    "type": "",
                    "raw_type": "",
                    "default": "",
                    "index": "",
                }
                continue

            if current_property is not None:
                if line.startswith("Prop Type :"):
                    raw_ref = self._clean_ref(line.split(":", 1)[1])
                    current_property["raw_type"] = raw_ref
                    current_property["type"] = raw_ref
                    continue
                if line.startswith("Default :"):
                    current_property["default"] = line.split(":", 1)[1].strip()
                    continue
                if line.startswith("Index :"):
                    current_property["index"] = line.split(":", 1)[1].strip()
                    continue
                if line.startswith("Storedaccess :"):
                    if current_property.get("visibility") == "published":
                        self.classes[current_class]["properties"].append(current_property)
                    current_property = None

        for item in self.types:
            item["type"] = self._resolve_ref(item["raw_ref"])
        for info in self.classes.values():
            if info.get("ancestor"):
                info["ancestor"] = self._resolve_ref(info["ancestor"])
            for prop in info["properties"]:
                prop["type"] = self._resolve_ref(prop["raw_type"])

    def _clean_ref(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def _extract_ref_id(self, ref: str, kind: str) -> str:
        match = re.search(rf"\b{kind}\s+(\d+)\b", ref)
        return match.group(1) if match else ""

    def _resolve_ref(self, ref: str) -> str:
        if ref == "Nil":
            return "Nil"
        unit_match = re.search(r"\bUnit\s+(\d+)\b", ref)
        if unit_match and unit_match.group(1) != "0":
            return ref
        sym_id = self._extract_ref_id(ref, "SymId")
        if sym_id and sym_id in self._symid_to_type:
            return self._symid_to_type[sym_id]
        def_id = self._extract_ref_id(ref, "DefId")
        if def_id and def_id in self._defid_to_type:
            return self._defid_to_type[def_id]
        return ref

    def print_summary(self):
        print(f"File: {self.filename}")
        print(f"\nTypes ({len(self.types)}):")
        for item in self.types:
            visibility = f" [{item['visibility']}]" if item["visibility"] else ""
            raw = f" ({item['raw_ref']})" if item["type"] != item["raw_ref"] else ""
            print(f"  - {item['name']}: {item['type']}{visibility}{raw}")

        print(f"\nClasses ({len(self.classes)}):")
        for class_name, info in self.classes.items():
            ancestor = f" < {info['ancestor']}" if info.get("ancestor") else ""
            print(f"  - {class_name}{ancestor}")
            for prop in info["properties"]:
                default = prop.get("default") or ""
                default_text = f", default={default}" if default else ""
                raw = f" ({prop['raw_type']})" if prop["type"] != prop["raw_type"] else ""
                print(f"      published property {prop['name']}: {prop['type']}{raw}{default_text}")


# ============================================================================
# Contoh Penggunaan
# ============================================================================

def main():
    arg_parser = argparse.ArgumentParser(
        description="Tampilkan daftar type, class, dan published property dari file .ppu."
    )
    arg_parser.add_argument("ppu_file", help="Path ke file .ppu")
    args = arg_parser.parse_args()
    ppu_file = args.ppu_file

    if not os.path.exists(ppu_file):
        print(f"File not found: {ppu_file}")
        sys.exit(1)

    ppudump_path = shutil.which("ppudump")
    if not ppudump_path:
        print("ppudump tidak ditemukan. Jalankan bppuparserpy.py untuk fallback Python eksperimental.")
        sys.exit(1)

    parser = PPUDumpSummaryParser(ppu_file, ppudump_path)
    parser.parse()
    parser.print_summary()


if __name__ == "__main__":
    main()

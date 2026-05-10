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
    USES_RE = re.compile(r"Uses unit:\s+(\S+)")

    def __init__(self, filename: str, ppudump_path: str = "ppudump"):
        self.filename = filename
        self.ppudump_path = ppudump_path
        self.used_units: List[str] = []
        self.types: List[Dict[str, str]] = []
        self.classes: Dict[str, Dict[str, Any]] = {}
        self._defs: Dict[str, Dict[str, Any]] = {}
        self._symid_to_type: Dict[str, str] = {}
        self._defid_to_type: Dict[str, str] = {}

    def parse(self):
        interface_text = self._run_ppudump("-VI")
        self._parse_interface_text(interface_text)

        definition_text = self._run_ppudump("-VDS")
        self._parse_definition_text(definition_text)

    def _run_ppudump(self, verbose: str) -> str:
        proc = subprocess.run(
            [self.ppudump_path, verbose, self.filename],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode not in (0, 217):
            raise RuntimeError((proc.stderr or proc.stdout).strip())
        return proc.stdout

    def _parse_interface_text(self, text: str):
        for line in text.splitlines():
            match = self.USES_RE.search(line)
            if match:
                self.used_units.append(match.group(1))

    def _parse_definition_text(self, text: str):
        current_def: Optional[Dict[str, str]] = None
        current_class: Optional[str] = None
        current_property: Optional[Dict[str, Any]] = None
        current_symbol: Optional[Dict[str, str]] = None
        current_enum_symbol: Optional[Dict[str, str]] = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            def_match = re.match(r"\*\* Definition Id (\d+) \*\*", line)
            if def_match:
                current_def = {
                    "id": def_match.group(1),
                    "kind": "",
                    "type_symbol_ref": "",
                    "details": {},
                    "collecting": True,
                }
                self._defs[current_def["id"]] = current_def
                current_property = None
                current_symbol = None
                current_enum_symbol = None
                continue

            if current_def and not current_def["kind"] and line in DEFINITION_LABELS:
                current_def["kind"] = line
                continue

            if line.startswith("Type symbol :") and current_def is not None:
                current_def["type_symbol_ref"] = self._clean_ref(line.split(":", 1)[1])
                continue

            if current_def is not None and (
                line.startswith("------")
                or line.startswith("Symtable options")
                or line.startswith("Symtable count")
            ):
                current_def["collecting"] = False

            if current_def is not None and current_def.get("collecting", False):
                self._collect_def_detail(current_def, line)

            class_match = self.CLASS_RE.search(line)
            if class_match and current_def is not None:
                current_class = class_match.group(1).strip()
                if self._should_skip_name(current_class):
                    continue
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
                current_enum_symbol = None
                current_property = None
                continue

            enum_match = re.search(r"Enumeration symbol\s+(.+)$", line)
            if enum_match and current_def is not None and current_def.get("kind") == "Enumeration type definition":
                current_enum_symbol = {"name": enum_match.group(1).strip(), "value": ""}
                current_def.setdefault("members", []).append(current_enum_symbol)
                continue

            if current_enum_symbol is not None and line.startswith("Value :"):
                current_enum_symbol["value"] = line.split(":", 1)[1].strip()
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
                name = current_symbol["name"]
                def_id = self._extract_ref_id(raw_ref, "DefId")
                def_info = self._defs.get(def_id, {}) if def_id else {}

                if not self._should_skip_name(name):
                    self._symid_to_type[current_symbol["id"]] = name
                def_id = self._extract_ref_id(raw_ref, "DefId")
                if def_id:
                    self._defid_to_type.setdefault(def_id, name)
                if self._include_type_symbol(name, def_info):
                    item = {
                        "name": name,
                        "sym_id": current_symbol["id"],
                        "visibility": current_symbol.get("visibility", ""),
                        "kind": self._display_kind(def_info.get("kind", "")),
                        "type": resolved,
                        "raw_ref": raw_ref,
                        "detail": self._format_type_detail(def_info),
                    }
                    self.types.append(item)
                current_symbol = None
                continue

            property_match = self.PROPERTY_RE.search(line)
            if property_match and current_class and not self._should_skip_name(current_class):
                prop_name = property_match.group(1).strip()
                if self._should_skip_name(prop_name):
                    current_property = None
                    continue
                current_property = {
                    "name": prop_name,
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

    def _collect_def_detail(self, definition: Dict[str, Any], line: str):
        fields = {
            "Element type": "element_type",
            "Range Type": "range_type",
            "Range": "range",
            "Options": "options",
            "Base type": "base_type",
            "Size": "size",
            "Set Base": "set_base",
            "Set Max": "set_max",
            "Smallest element": "smallest",
            "Largest element": "largest",
            "Return type": "return_type",
            "TypeOption": "type_option",
            "CallOption": "call_option",
            "Name of Record": "record_name",
            "DataSize": "data_size",
            "Pointed Type": "pointed_type",
            "String Encoding": "encoding",
            "Length": "length",
        }
        for label, key in fields.items():
            if line.startswith(f"{label} :"):
                definition["details"][key] = self._clean_ref(line.split(":", 1)[1])
                return

    def _clean_ref(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    def _extract_ref_id(self, ref: str, kind: str) -> str:
        match = re.search(rf"\b{kind}\s+(\d+)\b", ref)
        return match.group(1) if match else ""

    def _resolve_ref(self, ref: str) -> str:
        if ref == "Nil":
            return "Nil"
        unit_match = re.search(r"\bUnit\s+(\d+)\b", ref)
        if unit_match:
            return ref
        sym_id = self._extract_ref_id(ref, "SymId")
        if sym_id and sym_id in self._symid_to_type:
            return self._symid_to_type[sym_id]
        def_id = self._extract_ref_id(ref, "DefId")
        if def_id and def_id in self._defid_to_type:
            return self._defid_to_type[def_id]
        return ref

    def _include_type_symbol(self, name: str, definition: Dict[str, Any]) -> bool:
        if self._should_skip_name(name):
            return False
        kind = definition.get("kind", "")
        return kind not in {"Object/Class definition", "Class reference definition"}

    def _should_skip_name(self, name: str) -> bool:
        return "$vmt" in name.lower()

    def _display_kind(self, kind: str) -> str:
        return kind.replace(" definition", "").replace(" type", "").lower() or "type"

    def _format_type_detail(self, definition: Dict[str, Any], seen: Optional[set] = None) -> str:
        seen = seen or set()
        def_id = definition.get("id")
        if def_id:
            seen.add(def_id)
        kind = definition.get("kind", "")
        details = definition.get("details", {})

        if kind == "Set definition":
            element = self._describe_ref(details.get("element_type", ""), seen)
            return f"set of {element}".strip()
        if kind == "Array definition":
            element = self._describe_ref(details.get("element_type", ""), seen)
            range_text = details.get("range", "")
            options = details.get("options", "")
            suffix = f", range {range_text}" if range_text else ""
            if options:
                suffix += f", options {options}"
            return f"array of {element}{suffix}".strip()
        if kind == "Ordinal definition":
            base = details.get("base_type", "")
            range_text = details.get("range", "")
            return f"{base}, range {range_text}".strip(", ")
        if kind == "Enumeration type definition":
            smallest = details.get("smallest", "")
            largest = details.get("largest", "")
            size = details.get("size", "")
            parts = []
            members = definition.get("members", [])
            if members:
                parts.append(
                    "members "
                    + ", ".join(
                        f"{member['name']}={member['value']}" if member.get("value") else member["name"]
                        for member in members
                    )
                )
            if smallest or largest:
                parts.append(f"values {smallest}..{largest}")
            if size:
                parts.append(f"size {size}")
            return ", ".join(parts)
        if kind == "Record definition":
            record_name = details.get("record_name", "")
            data_size = details.get("data_size", "")
            return ", ".join(part for part in [record_name, f"size {data_size}" if data_size else ""] if part)
        if kind == "Pointer definition":
            pointed = self._describe_ref(details.get("pointed_type", ""), seen)
            return f"^ {pointed}".strip()
        if kind == "Procedural type (ProcVar) definition":
            return_type = self._describe_ref(details.get("return_type", ""), seen)
            type_option = details.get("type_option", "")
            call_option = details.get("call_option", "")
            return ", ".join(part for part in [type_option, f"returns {return_type}" if return_type else "", call_option] if part)
        if kind in {"ShortString definition", "AnsiString definition", "WideString definition", "UnicodeString definition", "Longstring definition"}:
            length = details.get("length", "")
            encoding = details.get("encoding", "")
            return ", ".join(part for part in [f"length {length}" if length else "", f"encoding {encoding}" if encoding else ""] if part)
        return ""

    def _describe_ref(self, ref: str, seen: Optional[set] = None) -> str:
        seen = seen or set()
        resolved = self._resolve_ref(ref)
        if resolved != ref:
            return resolved
        if re.search(r"\bUnit\s+\d+\b", ref):
            return ref
        def_id = self._extract_ref_id(ref, "DefId")
        if def_id in seen:
            return ref
        definition = self._defs.get(def_id, {}) if def_id else {}
        kind = definition.get("kind", "")
        details = definition.get("details", {})

        if kind == "Ordinal definition":
            base = details.get("base_type", "ordinal")
            range_text = details.get("range", "")
            return f"ordinal ({base}, range {range_text})" if range_text else f"ordinal ({base})"
        if kind == "Enumeration type definition":
            members = definition.get("members", [])
            if members:
                return "enum (" + ", ".join(
                    f"{member['name']}={member['value']}" if member.get("value") else member["name"]
                    for member in members
                ) + ")"
            smallest = details.get("smallest", "")
            largest = details.get("largest", "")
            return f"enum ({smallest}..{largest})" if smallest or largest else "enum"
        if kind == "Set definition":
            return self._format_type_detail(definition, seen)
        if kind == "Array definition":
            return self._format_type_detail(definition, seen)
        if kind == "Record definition":
            return details.get("record_name", ref)
        return ref

    def print_summary(self):
        print(f"File: {self.filename}")

        print(f"\nUses ({len(self.used_units)}):")
        for unit in self.used_units:
            print(f"  - {unit}")

        print(f"\nDeclared Types, excluding classes and $vmt ({len(self.types)}):")
        for item in self.types:
            visibility = f" [{item['visibility']}]" if item["visibility"] else ""
            detail = f" = {item['detail']}" if item.get("detail") else ""
            raw = f" ({item['raw_ref']})" if item["type"] != item["raw_ref"] else ""
            print(f"  - {item['name']}: {item['kind']}{detail}{visibility}{raw}")

        classes_with_props = {
            name: info for name, info in self.classes.items()
            if info["properties"] and not self._should_skip_name(name)
        }
        print(f"\nClasses with published properties ({len(classes_with_props)}):")
        for class_name, info in classes_with_props.items():
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

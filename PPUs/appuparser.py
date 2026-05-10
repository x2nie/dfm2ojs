"""
PPU (Free Pascal Unit) File Parser
Membaca struktur chunk, type declarations, dan published properties dari class
"""

import struct
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import IntEnum


class BlockType(IntEnum):
    """Block type untuk chunk PPU"""
    MAIN_BLOCK = 1
    NESTED_BLOCK = 2


class EntryIdentifier(IntEnum):
    """Entry identifier berdasarkan dokumentasi FPC[citation:1][citation:2]"""
    # General section
    IBMODULENAME = 1
    IBFILENAME = 2
    IBSOURCEFILES = 3
    IBUSEDMACROS = 4
    IBLOADUNIT = 5
    IBLINKUNITOFILES = 6
    IBLINKUNITSTATICLIBS = 7
    IBLINKUNITSHRDLIBS = 9
    IBENDINTERFACE = 10
    
    # Interface section
    IBSTARTDEFS = 20
    IBENDDEFS = 21
    IBSTARTSYMS = 22
    IBENDSYMS = 23
    IBTYPESYMREF = 30
    IBPROCSYMREF = 31
    
    # Implementation section
    IBENDIMPLEMENTATION = 40
    
    # Browser section
    IBENDBROWSER = 50
    
    # End
    IBEND = 255


@dataclass
class PPUHeader:
    """Header file PPU (28 bytes)[citation:3]"""
    magic: str                      # 'PPU' (3 bytes)
    version: str                    # e.g. '021' (3 bytes)
    compiler_major: int             # (1 byte)
    compiler_minor: int             # (1 byte)
    target_cpu: int                 # (2 bytes)
    target_os: int                  # (2 bytes)
    flags: int                      # (4 bytes)
    file_size: int                  # (4 bytes)
    crc_full: int                   # (4 bytes)
    crc_public: int                 # (4 bytes)
    reserved: bytes                 # (8 bytes)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'PPUHeader':
        """Parse header dari bytes (little-endian format[citation:3])"""
        if len(data) < 28:
            raise ValueError(f"Header too short: {len(data)} bytes")
        
        magic = data[0:3].decode('ascii')
        version = data[3:6].decode('ascii')
        compiler_major = data[6]
        compiler_minor = data[7]
        target_cpu = struct.unpack('<H', data[8:10])[0]
        target_os = struct.unpack('<H', data[10:12])[0]
        flags = struct.unpack('<I', data[12:16])[0]
        file_size = struct.unpack('<I', data[16:20])[0]
        crc_full = struct.unpack('<I', data[20:24])[0]
        crc_public = struct.unpack('<I', data[24:28])[0]
        reserved = data[28:36]
        
        return cls(
            magic=magic, version=version,
            compiler_major=compiler_major, compiler_minor=compiler_minor,
            target_cpu=target_cpu, target_os=target_os,
            flags=flags, file_size=file_size,
            crc_full=crc_full, crc_public=crc_public,
            reserved=reserved
        )


@dataclass
class PPUChunk:
    """Chunk data block dalam PPU[citation:1]"""
    block_type: BlockType
    identifier: int
    size: int
    data_offset: int
    data: Optional[bytes] = None
    
    @classmethod
    def read_from(cls, data: bytes, offset: int) -> Tuple['PPUChunk', int]:
        """Baca chunk dari bytes pada offset tertentu"""
        block_type = BlockType(data[offset])
        identifier = data[offset + 1]
        size = struct.unpack('<I', data[offset + 2:offset + 6])[0]
        
        chunk = cls(
            block_type=block_type,
            identifier=identifier,
            size=size,
            data_offset=offset + 6
        )
        
        # Baca data jika ada
        if size > 0 and offset + 6 + size <= len(data):
            chunk.data = data[offset + 6:offset + 6 + size]
        
        next_offset = offset + 6 + size
        return chunk, next_offset


@dataclass
class TypeInfo:
    """Informasi tipe data Pascal"""
    name: str
    kind: str                        # 'ordinal', 'set', 'enum', 'record', 'class', 'pointer', 'array'
    size: int = 0
    base_type: Optional[str] = None  # Untuk set, pointer, array
    range_min: Optional[int] = None  # Untuk ordinal types
    range_max: Optional[int] = None
    elements: List[str] = field(default_factory=list)  # Untuk enum atau set elements
    fields: List[Dict] = field(default_factory=list)   # Untuk record/class fields
    methods: List[str] = field(default_factory=list)
    properties: List[Dict] = field(default_factory=list)  # Published properties
    unit_index: int = 0              # Index unit untuk reference
    symbol_index: int = 0            # Index symbol dalam unit


@dataclass
class UsedUnit:
    """Unit yang digunakan (uses)"""
    name: str
    crc: int = 0
    index: int = 0


@dataclass
class SymbolReference:
    """Referensi ke symbol lain"""
    unit_index: int      # Index unit
    symbol_index: int    # Index symbol dalam unit tersebut
    name: str = ""


class PPUParser:
    """
    Parser untuk file PPU Free Pascal
    
    Berdasarkan dokumentasi:
    - Header format: docs.freepascal.org/prog/progse67.html[citation:3]
    - Chunk format: docs.freepascal.org/prog/progse68.html[citation:1]
    - Symbol management: deepwiki.com/fpc/FPCSource/2.1[citation:2]
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.header: Optional[PPUHeader] = None
        self.raw_data: Optional[bytes] = None
        self.chunks: List[PPUChunk] = []
        
        # Hasil parsing
        self.unit_name: str = ""
        self.used_units: List[UsedUnit] = []
        self.types: Dict[str, TypeInfo] = {}
        self.classes: Dict[str, TypeInfo] = {}
        self.published_properties: Dict[str, List[Dict]] = {}
        
    def parse(self):
        """Parse seluruh file PPU"""
        self._read_file()
        self._parse_header()
        self._parse_chunks()
        self._extract_type_info()
        
    def _read_file(self):
        """Baca seluruh file PPU"""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"PPU file not found: {self.filepath}")
        
        with open(self.filepath, 'rb') as f:
            self.raw_data = f.read()
    
    def _parse_header(self):
        """Parse header PPU (28 bytes)[citation:3]"""
        if len(self.raw_data) < 28:
            raise ValueError("Invalid PPU file: too small")
        
        self.header = PPUHeader.from_bytes(self.raw_data[:36])
        
        # Validasi magic number
        if self.header.magic != 'PPU':
            raise ValueError(f"Invalid PPU magic: {self.header.magic}")
        
        print(f"📁 PPU File: {self.filepath}")
        print(f"   Version: {self.header.version}")
        print(f"   Compiler: {self.header.compiler_major}.{self.header.compiler_minor}")
        print(f"   Flags: 0x{self.header.flags:08x}\n")
    
    def _parse_chunks(self):
        """Parse semua chunk dalam PPU[citation:1]"""
        offset = 36  # Setelah header (28 bytes header + 8 reserved = 36)
        
        while offset < len(self.raw_data):
            try:
                chunk, offset = PPUChunk.read_from(self.raw_data, offset)
                self.chunks.append(chunk)
            except Exception as e:
                print(f"Warning: Error parsing chunk at offset {offset}: {e}")
                break
    
    def _extract_type_info(self):
        """Ekstrak informasi tipe, class, dan properti dari chunks"""
        
        for chunk in self.chunks:
            if chunk.identifier == EntryIdentifier.IBMODULENAME:
                self._parse_modulename(chunk)
            elif chunk.identifier == EntryIdentifier.IBLOADUNIT:
                self._parse_used_units(chunk)
            elif chunk.identifier in [EntryIdentifier.IBTYPESYMREF, 30]:  # Type definition
                self._parse_type_definition(chunk)
            elif chunk.identifier == EntryIdentifier.IBSTARTSYMS:
                self._parse_symbols(chunk)
    
    def _parse_modulename(self, chunk: PPUChunk):
        """Parse nama unit dari chunk"""
        if chunk.data:
            self.unit_name = self._read_pascal_string(chunk.data, 0)[0]
            print(f"📦 Unit name: {self.unit_name}")
    
    def _parse_used_units(self, chunk: PPUChunk):
        """Parse daftar unit yang digunakan (uses)[citation:1]"""
        if not chunk.data:
            return
        
        offset = 0
        while offset < len(chunk.data):
            name, offset = self._read_pascal_string(chunk.data, offset)
            if offset + 4 <= len(chunk.data):
                crc = struct.unpack('<I', chunk.data[offset:offset+4])[0]
                offset += 4
                used_unit = UsedUnit(name=name, crc=crc, index=len(self.used_units))
                self.used_units.append(used_unit)
                print(f"   Uses: {name} (CRC: 0x{crc:08x})")
            else:
                break
    
    def _parse_type_definition(self, chunk: PPUChunk):
        """Parse type definition"""
        if not chunk.data:
            return
        
        # Format sederhana: [kind (1 byte)] [name] [data]
        offset = 0
        if offset < len(chunk.data):
            kind = chunk.data[offset]
            offset += 1
            
            type_name, offset = self._read_pascal_string(chunk.data, offset)
            
            type_info = TypeInfo(name=type_name, kind=self._get_type_kind_name(kind))
            
            # Parse berdasarkan kind
            if kind in [1, 2, 3]:  # Ordinal types
                if offset + 8 <= len(chunk.data):
                    type_info.range_min = struct.unpack('<i', chunk.data[offset:offset+4])[0]
                    type_info.range_max = struct.unpack('<i', chunk.data[offset+4:offset+8])[0]
                    offset += 8
            elif kind == 4:  # Enum
                self._parse_enum_type(type_info, chunk.data, offset)
            elif kind == 5:  # Set
                type_info.kind = 'set'
                if offset < len(chunk.data):
                    base_type_idx = chunk.data[offset]
                    type_info.base_type = f"[base_type_{base_type_idx}]"
            elif kind == 7:  # Class/object
                type_info.kind = 'class'
                self._parse_class_type(type_info, chunk.data, offset)
            
            self.types[type_name] = type_info
            if type_info.kind == 'class':
                self.classes[type_name] = type_info
    
    def _parse_enum_type(self, type_info: TypeInfo, data: bytes, offset: int):
        """Parse enum type"""
        type_info.kind = 'enum'
        elem_count = data[offset] if offset < len(data) else 0
        offset += 1
        
        for i in range(elem_count):
            if offset >= len(data):
                break
            elem_name, offset = self._read_pascal_string(data, offset)
            type_info.elements.append(elem_name)
            offset += 4  # Skip ordinal value
    
    def _parse_class_type(self, type_info: TypeInfo, data: bytes, offset: int):
        """Parse class definition - mencari published properties[citation:2]"""
        
        # Skip class flags dan parent reference
        if offset + 2 <= len(data):
            flags = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
        
        # Baca fields
        field_count = data[offset] if offset < len(data) else 0
        offset += 1
        
        for _ in range(field_count):
            if offset >= len(data):
                break
            field_name, offset = self._read_pascal_string(data, offset)
            field_type_idx = data[offset] if offset < len(data) else 0
            offset += 1
            type_info.fields.append({
                'name': field_name,
                'type_ref': field_type_idx,
                'type_ref_desc': f"[unit_index: ?, symbol_index: {field_type_idx}]"
            })
        
        # Baca methods (skip)
        method_count = data[offset] if offset < len(data) else 0
        offset += 1
        for _ in range(method_count):
            method_name, offset = self._read_pascal_string(data, offset)
            type_info.methods.append(method_name)
            offset += 2  # Skip method flags
        
        # Baca published properties
        prop_count = data[offset] if offset < len(data) else 0
        offset += 1
        
        for _ in range(prop_count):
            prop_name, offset = self._read_pascal_string(data, offset)
            
            # Property type reference: [unit_index, symbol_index]
            if offset + 4 <= len(data):
                unit_idx = struct.unpack('<H', data[offset:offset+2])[0]
                sym_idx = struct.unpack('<H', data[offset+2:offset+4])[0]
                offset += 4
                
                prop_info = {
                    'name': prop_name,
                    'unit_index': unit_idx,
                    'symbol_index': sym_idx,
                    'type_ref': f"[{unit_idx}, {sym_idx}]",
                    'read_method': None,
                    'write_method': None
                }
                
                # Baca access methods (read/write)
                if offset + 2 <= len(data):
                    read_ref = struct.unpack('<H', data[offset:offset+2])[0]
                    write_ref = struct.unpack('<H', data[offset+2:offset+4])[0]
                    offset += 4
                    prop_info['read_method'] = read_ref if read_ref != 0xFFFF else None
                    prop_info['write_method'] = write_ref if write_ref != 0xFFFF else None
                
                type_info.properties.append(prop_info)
    
    def _parse_symbols(self, chunk: PPUChunk):
        """Parse symbol section (ibstartsyms)"""
        # Symbol parsing lebih kompleks, memerlukan full implementation dari ppu.pas
        pass
    
    def _get_type_kind_name(self, kind: int) -> str:
        """Konversi kind byte ke nama tipe"""
        kind_map = {
            1: 'ordinal', 2: 'ordinal', 3: 'ordinal',
            4: 'enum', 5: 'set', 6: 'array',
            7: 'class', 8: 'record', 9: 'pointer'
        }
        return kind_map.get(kind, f'unknown_{kind}')
    
    def _read_pascal_string(self, data: bytes, offset: int) -> Tuple[str, int]:
        """Baca Pascal string (panjang byte diikuti data)"""
        if offset >= len(data):
            return "", offset
        length = data[offset]
        offset += 1
        if length == 0 or offset + length > len(data):
            return "", offset
        string_data = data[offset:offset + length].decode('ascii', errors='replace')
        return string_data, offset + length
    
    def get_used_units(self) -> List[str]:
        """Dapatkan daftar unit yang digunakan (array uses unit)"""
        return [u.name for u in self.used_units]
    
    def get_types(self) -> Dict[str, TypeInfo]:
        """Dapatkan semua type declarations"""
        return self.types
    
    def get_classes(self) -> Dict[str, TypeInfo]:
        """Dapatkan semua class yang dideklarasikan"""
        return {name: cls for name, cls in self.classes.items()}
    
    def get_published_properties(self, class_name: str = None) -> Dict[str, List[Dict]]:
        """
        Dapatkan published properties dari class
        
        Format return: {
            'class_name': [
                {'name': 'Prop1', 'unit_index': 0, 'symbol_index': 123, 'type_ref': '[0, 123]'},
                ...
            ]
        }
        """
        if class_name:
            if class_name in self.classes:
                return {class_name: self.classes[class_name].properties}
            return {}
        return {name: cls.properties for name, cls in self.classes.items()}
    
    def print_summary(self):
        """Print ringkasan hasil parsing"""
        print("\n" + "="*60)
        print("📊 PPU FILE SUMMARY")
        print("="*60)
        
        print(f"\n📦 Unit: {self.unit_name}")
        
        print(f"\n📚 Used Units ({len(self.used_units)}):")
        for u in self.used_units:
            print(f"   - {u.name}")
        
        print(f"\n🔧 Type Declarations ({len(self.types)}):")
        for name, t in self.types.items():
            if t.kind == 'enum':
                elems = ', '.join(t.elements[:5])
                if len(t.elements) > 5:
                    elems += f", ... ({len(t.elements)} total)"
                print(f"   - {name}: {t.kind} ({elems})")
            elif t.kind == 'set':
                print(f"   - {name}: set of {t.base_type}")
            elif t.kind == 'class':
                props = len(t.properties)
                print(f"   - {name}: class ({len(t.fields)} fields, {len(t.methods)} methods, {props} properties)")
            else:
                print(f"   - {name}: {t.kind}")
        
        print(f"\n🏛️ Classes with Published Properties:")
        for name, cls in self.classes.items():
            if cls.properties:
                print(f"\n   📗 {name}:")
                for prop in cls.properties:
                    print(f"      - {prop['name']}: {prop['type_ref']}")
            else:
                print(f"   📗 {name}: (no published properties)")
        
        print("="*60)
    
    def print_published_properties_table(self):
        """Print tabel published properties dengan format yang diminta"""
        print("\n" + "-"*80)
        print(f"{'CLASS':<25} {'PROPERTY':<20} {'TYPE REFERENCE':<20} {'READ':<10} {'WRITE':<10}")
        print("-"*80)
        
        for class_name, cls in self.classes.items():
            if cls.properties:
                for prop in cls.properties:
                    type_ref = f"[{prop['unit_index']}, {prop['symbol_index']}]"
                    read_meth = prop['read_method'] if prop['read_method'] else '-'
                    write_meth = prop['write_method'] if prop['write_method'] else '-'
                    print(f"{class_name:<25} {prop['name']:<20} {type_ref:<20} {read_meth:<10} {write_meth:<10}")
            else:
                print(f"{class_name:<25} {'(no published properties)':<20} {'-':<20} {'-':<10} {'-':<10}")
        print("-"*80)


# ============= Contoh Penggunaan =============

def main():
    """Contoh penggunaan PPU Parser"""
    
    # Ganti dengan path file PPU Anda
    ppu_file = "example.ppu"  # Contoh: "system.ppu", "classes.ppu", dll.
    ppu_file = "sysutils.ppu"
    ppu_file = "types.ppu"
    
    if not os.path.exists(ppu_file):
        print(f"❌ File tidak ditemukan: {ppu_file}")
        print("\nGunakan file .ppu dari hasil kompilasi Free Pascal")
        print("Contoh: system.ppu, classes.ppu, sysutils.ppu")
        return
    
    try:
        # Inisialisasi parser
        parser = PPUParser(ppu_file)
        
        # Parse file
        parser.parse()
        
        # 1. Scan uses unit (array)
        print("\n" + "="*60)
        print("1️⃣ USES UNITS (Array)")
        print("="*60)
        used_units = parser.get_used_units()
        for i, unit in enumerate(used_units):
            print(f"   [{i}] {unit}")
        
        # 2. Type declarations (termasuk set, set of, dll)
        print("\n" + "="*60)
        print("2️⃣ TYPE DECLARATIONS")
        print("="*60)
        for type_name, type_info in parser.get_types().items():
            print(f"\n   📐 {type_name} ({type_info.kind})")
            if type_info.kind == 'set':
                print(f"      └─ set of {type_info.base_type}")
            elif type_info.kind == 'enum':
                print(f"      └─ ({', '.join(type_info.elements)})")
            elif type_info.kind in ['ordinal']:
                if type_info.range_min is not None:
                    print(f"      └─ range {type_info.range_min}..{type_info.range_max}")
        
        # 3. Class names
        print("\n" + "="*60)
        print("3️⃣ CLASS NAMES")
        print("="*60)
        for class_name in parser.get_classes().keys():
            print(f"   🏛️ {class_name}")
        
        # 4. Published Properties dengan type reference [unit index, symbol index]
        print("\n" + "="*60)
        print("4️⃣ PUBLISHED PROPERTIES")
        print("="*60)
        for class_name, props in parser.get_published_properties().items():
            if props:
                print(f"\n   📗 {class_name}:")
                for prop in props:
                    print(f"      ├─ {prop['name']} : [{prop['unit_index']}, {prop['symbol_index']}]")
                    if prop['read_method']:
                        print(f"      │   └─ read: {prop['read_method']}")
                    if prop['write_method']:
                        print(f"      └─ write: {prop['write_method']}")
            else:
                print(f"\n   📗 {class_name}: (no published properties)")
        
        # Print tabel ringkas
        parser.print_published_properties_table()
        
        # Print summary lengkap
        parser.print_summary()
        
    except Exception as e:
        print(f"❌ Error parsing PPU file: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
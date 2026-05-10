"""
Raw/experimental PPU parser fallback.

File ini berisi parser Python langsung untuk struktur .ppu. Parser utama
(appuparser.py) sengaja membaca output ppudump karena format PPU lebih aman
mengikuti implementasi FPC resmi.
"""

import struct
import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import IntEnum


class EntryIdentifier(IntEnum):
    """Entry identifiers (ib... constants dari ppu.pas)"""
    IBERROR = 0
    IBMODULENAME = 1
    IBSOURCEFILES = 2
    IBLOADUNIT = 3
    IBINITUNIT = 4
    IBLINKUNITOFILES = 5
    IBLINKUNITSTATICLIBS = 6
    IBLINKUNITSHRDLIBS = 7
    IBLINKOTHEROFILS = 8
    IBLINKOTHERSTATICLIBS = 9
    IBLINKOTHERSHRDLIBS = 10
    IBIMPORTSYMBOLS = 11
    IBSYMREF = 12
    IBDEFREF = 13
    IBFEATURES = 14
    IBUSEDMACROS = 16
    IBDEREFDATA = 17
    IBEXPORTEDMACROS = 18
    IBDEREFMAP = 19
    IBTYPESYM = 20
    IBPROCSYM = 21
    IBSTATICVARSYM = 22
    IBCONSTSYM = 23
    IBENUMSYM = 24
    IBTYPEDCONSTSYM = 25
    IBABSOLUTEVARSYM = 26
    IBPROPERTYSYM = 27
    IBFIELDVARSYM = 28
    IBUNITSYM = 29
    IBLABELSYM = 30
    IBSYSSYM = 31
    IBNAMESPACESYM = 32
    IBLOCALVARSYM = 33
    IBPARAVARSYM = 34
    IBMACROSYM = 35
    IBORDDEF = 40
    IBPOINTERDEF = 41
    IBARRAYDEF = 42
    IBPROCDEF = 43
    IBSHORTSTRINGDEF = 44
    IBRECORDDEF = 45
    IBFILEDEF = 46
    IBFORMALDEF = 47
    IBOBJECTDEF = 48
    IBENUMDEF = 49
    IBSETDEF = 50
    IBPROCVARDEF = 51
    IBFLOATDEF = 52
    IBCLASSREFDEF = 53
    IBLONGSTRINGDEF = 54
    IBANSISTRINGDEF = 55
    IBWIDESTRINGDEF = 56
    IBVARIANTDEF = 57
    IBUNDEFINEDDEF = 58
    IBUNICODESTRINGDEF = 59
    IBNODETREE = 80
    IBASMSYMBOLS = 81
    IBRESOURCES = 82
    IBCREATEDOBJTYPES = 83
    IBWPOFILE = 84
    IBMODULEOPTIONS = 85
    IBUNITIMPORTSYMS = 86
    IBMAINNAME = 90
    IBSYMTABLEOPTIONS = 91
    IBPACKAGEFILES = 92
    IBPACKAGENAME = 93
    IBRECSYMTABLEOPTIONS = 94
    IBLINKOTHERFRAMEWORKS = 100
    IBJVMNAMESPACE = 101
    IBSTARTDEFS = 248
    IBENDDEFS = 249
    IBSTARTSYMS = 250
    IBENDSYMS = 251
    IBENDINTERFACE = 252
    IBENDIMPLEMENTATION = 253
    IBENDBROWSER = 254
    IBEND = 255


class PPUVersion:
    """Versi PPU yang didukung"""
    CURRENT_PPU_VERSION = 207  # FPC 3.2.x


@dataclass
class PPUHeaderCommon:
    """Header umum PPU (32 bytes)"""
    magic: str                    # 'PPU'
    version_tag: str              # 'xxx'
    compiler: int                 # versi compiler (major<<14 + minor<<7 + patch)
    cpu: int                      # target CPU
    target: int                   # target OS
    flags: int                    # unit flags
    size: int                     # ukuran file (tanpa header)
    checksum: int                 # CRC
    interface_checksum: int       # CRC interface
    indirect_checksum: int        # CRC indirect
    deflistsize: int              # jumlah definisi
    symlistsize: int              # jumlah symbol
    # ... sisanya 8 bytes reserved


@dataclass
class PPUHeader:
    """Header lengkap PPU dengan data tambahan"""
    common: PPUHeaderCommon
    # Data tambahan dari header extension jika ada


@dataclass 
class PPUEntry:
    """tppuentry dari FPC"""
    next_offset: int        # offset ke entry berikutnya (-1 = last)
    hash: int               # hash value untuk pencarian
    name_ref: int           # offset ke string table
    entry_type: int         # tipe entry
    flags: int              # flags (opsional)
    data_offset: int        # offset ke data
    data_size: int          # ukuran data
    name: str = ""          # nama (di-resolve dari string table)


@dataclass
class LoadedUnit:
    """Unit yang di-load (dari ibloadunit)"""
    name: str
    crc: int
    interface_crc: int
    indirect_crc: int
    index: int = 0


class PPUFileReader:
    """
    Reader untuk file PPU berdasarkan implementasi FPC
    
    Struktur file PPU:
    [ Header: 32+ bytes ]
    [ Interface Section ]
        - ibmodulename
        - ibloadunit (uses units)
        - ibsourcefiles
        - ibderefdata (untuk referensi)
        - ibstartdefs / ibenddefs
        - ibstartsyms / ibendsyms
    [ Implementation Section ]
        - ibasmsymbols
        - ibloadunit (implementation uses)
        - ibunitimportsyms
        - ibendimplementation
    """
    
    def __init__(self, filename: str):
        self.filename = filename
        self.data: Optional[bytes] = None
        self.pos: int = 0
        self.header: Optional[PPUHeader] = None
        self.change_endian: bool = False
        
        # Hasil parsing
        self.unit_name: str = ""
        self.used_units: List[LoadedUnit] = []
        self.strings: Dict[int, str] = {}  # offset -> string
        self.deref_data: Optional[bytes] = None  # data untuk dereference
        self.ref_units: List[str] = []  # deref map
        
        # Entries
        self.entries: List[PPUEntry] = []
        
        # Hasil akhir
        self.classes: Dict[str, Dict] = {}
        self.published_properties: Dict[str, List[Dict]] = {}
        self.current_class_name: Optional[str] = None
        
    def read_byte(self) -> int:
        """Baca 1 byte"""
        if self.pos >= len(self.data):
            raise EOFError("Unexpected end of file")
        b = self.data[self.pos]
        self.pos += 1
        return b
    
    def read_word(self) -> int:
        """Baca 2 bytes (little-endian)"""
        val = struct.unpack('<H', self.data[self.pos:self.pos+2])[0]
        if self.change_endian:
            val = ((val >> 8) & 0xFF) | ((val & 0xFF) << 8)
        self.pos += 2
        return val
    
    def read_dword(self) -> int:
        """Baca 4 bytes (little-endian)"""
        val = struct.unpack('<I', self.data[self.pos:self.pos+4])[0]
        if self.change_endian:
            val = ((val >> 24) & 0xFF) | ((val >> 8) & 0xFF00) | \
                  ((val & 0xFF00) << 8) | ((val & 0xFF) << 24)
        self.pos += 4
        return val
    
    def read_longint(self) -> int:
        """Baca signed 4 bytes"""
        return self.read_dword()
    
    def read_string(self) -> str:
        """Baca Pascal string (panjang byte diikuti data)"""
        length = self.read_byte()
        if length == 0:
            return ""
        if self.pos + length > len(self.data):
            raise ValueError("String exceeds file bounds")
        s = self.data[self.pos:self.pos+length].decode('ascii', errors='replace')
        self.pos += length
        return s
    
    def read_ansistring(self) -> str:
        """Baca ansistring (panjang 4 bytes diikuti data)"""
        length = self.read_dword()
        if length == 0:
            return ""
        if self.pos + length > len(self.data):
            raise ValueError("String exceeds file bounds")
        s = self.data[self.pos:self.pos+length].decode('ascii', errors='replace')
        self.pos += length
        return s
    
    def skip(self, count: int):
        """Skip sejumlah bytes"""
        if count > 0:
            self.pos += count
        
    def read_entry(self) -> int:
        """
        Baca entry identifier (seperti readentry di ppudump.pp)
        Returns entry identifier atau iberror jika error
        """
        try:
            # tentry = packed record size: longint; id: byte; nr: byte; end
            size = self.read_dword()
            block_type = self.read_byte()
            identifier = self.read_byte()
            
            # simpan posisi data
            self.current_entry_size = size
            self.current_entry_start = self.pos
            self.current_entry_identifier = identifier
            self.current_entry_block_type = block_type
            
            return identifier
        except Exception:
            return EntryIdentifier.IBERROR
    
    def end_of_entry(self) -> bool:
        """Cek apakah sudah sampai akhir entry"""
        return self.pos >= self.current_entry_start + self.current_entry_size
    
    def parse(self):
        """Parse seluruh file PPU"""
        self._read_file()
        self._parse_header()
        self._parse_interface_section()
        self._parse_implementation_section()
        
    def _read_file(self):
        """Baca file ke memory"""
        if not os.path.exists(self.filename):
            raise FileNotFoundError(f"PPU file not found: {self.filename}")
        
        with open(self.filename, 'rb') as f:
            self.data = f.read()
        self.pos = 0
    
    def _parse_header(self):
        """Parse header PPU (32 bytes) - berdasarkan ppudump.pp"""
        if len(self.data) < 32:
            raise ValueError("File too small for PPU header")
        
        magic = self.data[0:3].decode('ascii')
        if magic != 'PPU':
            raise ValueError(f"Invalid PPU magic: {magic}")
        
        version_tag = self.data[3:6].decode('ascii')
        compiler = struct.unpack('<I', self.data[6:10])[0]
        cpu = struct.unpack('<H', self.data[10:12])[0]
        target = struct.unpack('<H', self.data[12:14])[0]
        flags = struct.unpack('<I', self.data[14:18])[0]
        size = struct.unpack('<I', self.data[18:22])[0]
        checksum = struct.unpack('<I', self.data[22:26])[0]
        interface_checksum = struct.unpack('<I', self.data[26:30])[0]
        indirect_checksum = struct.unpack('<I', self.data[30:34])[0]
        deflistsize = struct.unpack('<I', self.data[34:38])[0]
        symlistsize = struct.unpack('<I', self.data[38:42])[0]
        
        self.header = PPUHeader(
            common=PPUHeaderCommon(
                magic=magic,
                version_tag=version_tag,
                compiler=compiler,
                cpu=cpu,
                target=target,
                flags=flags,
                size=size,
                checksum=checksum,
                interface_checksum=interface_checksum,
                indirect_checksum=indirect_checksum,
                deflistsize=deflistsize,
                symlistsize=symlistsize
            )
        )
        
        self.pos = 42  # setelah header 42 bytes (32 + 10)
        
        # Cek endianness
        if (flags & 0x4) != 0:  # big_endian flag
            self.change_endian = True
        
        version = self.header.common.version_tag
        print(f"📁 {self.filename}")
        print(f"   PPU Version: {version}")
        print(f"   Compiler: {(compiler >> 14) & 0x7F}.{(compiler >> 7) & 0x7F}.{compiler & 0x7F}")
        print(f"   Target: {self._target_to_str(target)}")
        print(f"   Flags: 0x{flags:08x}")
        print()
    
    def _target_to_str(self, target: int) -> str:
        """Konversi target OS ke string"""
        targets = {
            3: "Linux-i386",
            5: "Win32",
            26: "Linux-x86-64",
            37: "Win64-x64",
            61: "Darwin-x64",
            # ... tambahan sesuai systems.inc
        }
        return targets.get(target, f"Unknown({target})")
    
    def _parse_interface_section(self):
        """Parse interface section"""
        print("📖 INTERFACE SECTION")
        print("-" * 50)
        
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDINTERFACE:
                print("   End of interface section")
                break
            elif entry_id == EntryIdentifier.IBMODULENAME:
                self.unit_name = self.read_string()
                print(f"   Module name: {self.unit_name}")
            elif entry_id == EntryIdentifier.IBLOADUNIT:
                self._parse_load_unit()
            elif entry_id == EntryIdentifier.IBSOURCEFILES:
                self._parse_source_files()
            elif entry_id == EntryIdentifier.IBDEREFDATA:
                self._parse_deref_data()
            elif entry_id == EntryIdentifier.IBDEREFMAP:
                self._parse_deref_map()
            elif entry_id == EntryIdentifier.IBSTARTDEFS:
                print("   Starting definitions...")
                self._parse_definitions()
            elif entry_id == EntryIdentifier.IBSTARTSYMS:
                print("   Starting symbols...")
                self._parse_symbols()
            elif entry_id == 0 or entry_id == 255:
                break
            else:
                print(f"   Skipping entry {entry_id} (size={self.current_entry_size})")
                self.skip(self.current_entry_size)
            
            if not self.end_of_entry() and self.current_entry_size > 0:
                print(f"      Warning: {self.current_entry_size - (self.pos - self.current_entry_start)} bytes left")
    
    def _parse_load_unit(self):
        """Parse ibloadunit - unit yang digunakan (uses)"""
        while not self.end_of_entry():
            name = self.read_string()
            crc = self.read_dword()
            intf_crc = self.read_dword()
            ind_crc = self.read_dword()
            
            unit = LoadedUnit(
                name=name,
                crc=crc,
                interface_crc=intf_crc,
                indirect_crc=ind_crc,
                index=len(self.used_units)
            )
            self.used_units.append(unit)
            print(f"   Uses: {name} (CRC: 0x{crc:08x})")
    
    def _parse_source_files(self):
        """Parse ibsourcefiles"""
        idx = 1
        while not self.end_of_entry():
            name = self.read_string()
            timestamp = self.read_longint()
            print(f"   Source {idx}: {name}")
            idx += 1
    
    def _parse_deref_data(self):
        """Parse ibderefdata - data untuk dereference"""
        self.deref_data = self.data[self.pos:self.pos + self.current_entry_size]
        print(f"   Deref data size: {len(self.deref_data)} bytes")
        self.skip(self.current_entry_size)
    
    def _parse_deref_map(self):
        """Parse ibderefmap - mapping untuk referensi unit"""
        map_size = self.read_dword()
        print(f"   Deref map size: {map_size}")
        
        for i in range(map_size):
            unit_name = self.read_string()
            self.ref_units.append(unit_name.lower())
            print(f"      [{i}] {unit_name}")
    
    def _parse_definitions(self):
        """Parse definisi tipe - berdasarkan readdefinitions di ppudump.pp"""
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDDEFS:
                break
            elif entry_id == EntryIdentifier.IBOBJECTDEF:
                self._parse_object_definition()
            elif entry_id == EntryIdentifier.IBRECORDDEF:
                self._parse_record_definition()
            elif entry_id == EntryIdentifier.IBPROCDEF:
                self._parse_proc_definition()
            elif entry_id == EntryIdentifier.IBPOINTERDEF:
                self._parse_pointer_definition()
            elif entry_id == EntryIdentifier.IBARRAYDEF:
                self._parse_array_definition()
            else:
                # Skip definisi yang tidak dikenal
                self.skip(self.current_entry_size)
            
            if not self.end_of_entry() and self.current_entry_size > 0:
                # Ada sisa data yang belum dibaca
                pass
    
    def _parse_object_definition(self):
        """
        Parse object/class definition - berdasarkan ibobjectdef di ppudump.pp
        
        Struktur:
        - DefId (4 bytes)
        - Name (string)
        - Import lib/pkg (string)
        - Object options (smallset)
        - Object type (byte)
        - Helper type (byte)
        - External name (string)
        - DataSize (asizeint)
        - PaddingSize (word)
        - FieldAlign (shortint)
        - RecordAlign (shortint)
        - RecordAlignMin (shortint)
        - VmtField (deref)
        - Ancestor Class (deref)
        - IIDGUID (16 bytes, optional)
        - IID String (string, optional)
        - Abstract methods count (longint)
        - VMT entries count (longint)
        - Implemented interfaces count (longint)
        - Fields symtable (nested)
        """
        
        # Baca def id
        def_id = self.read_longint()
        
        # Baca nama class
        class_name = self.read_string()
        
        # Baca import lib/pkg
        import_lib = self.read_string()
        
        # Baca object options
        obj_options = self._read_smallset()
        
        # Baca object type
        obj_type = self.read_byte()
        obj_type_str = self._object_type_to_str(obj_type)
        
        # Baca helper type
        helper_type = self.read_byte()
        
        # Baca external name
        ext_name = self.read_string()
        
        # Baca DataSize
        data_size = self.read_dword()
        
        # Baca PaddingSize
        padding_size = self.read_word()
        
        # Baca FieldAlign
        field_align = self.read_byte()
        
        # Baca RecordAlign
        record_align = self.read_byte()
        
        # Baca RecordAlignMin
        record_align_min = self.read_byte()
        
        # Baca VmtField (deref)
        vmt_field = self._read_deref()
        
        # Baca Ancestor Class (deref)
        ancestor = self._read_deref()
        
        # Jika interface, baca GUID
        iid_string = ""
        if obj_type in [0x02, 0x03, 0x05]:  # interface types
            # Skip 16 byte GUID
            self.skip(16)
            iid_string = self.read_string()
        
        # Baca abstract methods count
        abstract_count = self.read_longint()
        
        # Baca VMT entries count
        vmt_count = self.read_longint()
        
        # Skip VMT entries
        for _ in range(vmt_count):
            self._read_deref()
            self.read_byte()  # visibility
        
        # Baca implemented interfaces count
        impl_intf_count = self.read_longint()
        
        # Skip implemented interfaces
        for _ in range(impl_intf_count):
            self._read_deref()  # definition
            self._read_deref()  # getter def
            self.read_longint()  # IOffset
            self.read_byte()  # entry type
        
        # Simpan informasi class
        class_info = {
            'name': class_name,
            'def_id': def_id,
            'obj_type': obj_type_str,
            'ancestor': ancestor,
            'data_size': data_size,
            'properties': []  # akan diisi dari symbol section
        }
        
        self.classes[class_name] = class_info
        self.current_class_name = class_name
        print(f"   📗 Class: {class_name} ({obj_type_str})")
        if ancestor:
            print(f"      Ancestor: {ancestor}")
        
        # Selanjutnya ada symtable untuk fields, tapi skip untuk sekarang
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_record_definition(self):
        """Parse record definition"""
        def_id = self.read_longint()
        record_name = self.read_string()
        print(f"   📘 Record: {record_name}")
        
        # Skip sisanya
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_proc_definition(self):
        """Parse procedure definition"""
        def_id = self.read_longint()
        # Skip untuk sekarang
        self.skip(self.current_entry_size - 4)
    
    def _parse_pointer_definition(self):
        """Parse pointer definition"""
        def_id = self.read_longint()
        self.skip(self.current_entry_size - 4)
    
    def _parse_array_definition(self):
        """Parse array definition"""
        def_id = self.read_longint()
        self.skip(self.current_entry_size - 4)
    
    def _parse_symbols(self):
        """Parse symbols - berdasarkan readSymbols di ppudump.pp"""
        # Baca symtable count
        sym_count = self.read_longint()
        print(f"   Symbol count: {sym_count}")
        
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDSYMS:
                break
            elif entry_id == EntryIdentifier.IBPROPERTYSYM:
                self._parse_property_symbol()
            elif entry_id == EntryIdentifier.IBTYPESYM:
                self._parse_type_symbol()
            elif entry_id == EntryIdentifier.IBPROCSYM:
                self._parse_proc_symbol()
            elif entry_id == EntryIdentifier.IBCONSTSYM:
                self._parse_const_symbol()
            elif entry_id == EntryIdentifier.IBFIELDVARSYM:
                self._parse_field_var_sym()
            else:
                # Skip symbol yang tidak dikenal
                self.skip(self.current_entry_size)
            
            if not self.end_of_entry() and self.current_entry_size > 0:
                pass
    
    def _parse_property_symbol(self):
        """
        Parse property symbol - ini yang Anda cari untuk published properties!
        
        Struktur berdasarkan readpropertysym di ppudump.pp:
        - Symbol name (string)
        - SymId (longint)
        - FilePos info
        - Visibility (byte)
        - SymOptions (smallset)
        - PropOptions (smallset)
        - OverrideProp (deref, optional)
        - PropType (deref)
        - Index (longint)
        - Default (longint)
        - IndexType (deref)
        - Noneaccess (propaccesslist)
        - Readaccess (propaccesslist)
        - Writeaccess (propaccesslist)
        - Storedaccess (propaccesslist)
        - Param symtable (optional)
        """
        
        # Baca nama property
        prop_name = self.read_string()
        
        # Baca SymId
        sym_id = self.read_longint()
        
        # Baca FilePos
        self._read_filepos()
        
        # Baca Visibility
        visibility = self.read_byte()
        
        # Baca SymOptions
        sym_options = self._read_smallset()
        
        # Baca PropOptions
        prop_options = self._read_smallset()
        
        # Cek apakah override
        if 7 in prop_options:  # ppo_overrides
            override_prop = self._read_deref()
        
        # Baca PropType (ini adalah tipe property dalam format [unit, symbol])
        prop_type = self._read_deref()
        
        # Baca Index, Default
        index_val = self.read_longint()
        default_val = self.read_longint()
        
        # Baca IndexType
        index_type = self._read_deref()
        
        # Baca Noneaccess (skip)
        self._read_prop_access_list()
        
        # Baca Readaccess - ini yang penting
        read_access = self._read_prop_access_list(return_ref=True)
        
        # Baca Writeaccess
        write_access = self._read_prop_access_list(return_ref=True)
        
        # Baca Storedaccess
        self._read_prop_access_list()
        
        # Cek apakah ada parameters
        if 4 in prop_options:  # ppo_hasparameters
            # Skip param symtable
            self._skip_symtable()
        
        if visibility != 6:  # vis_published
            self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
            return

        # Simpan published property
        prop_info = {
            'name': prop_name,
            'sym_id': sym_id,
            'visibility': visibility,
            'type_ref': prop_type,
            'read_ref': read_access,
            'write_ref': write_access,
            'index': index_val,
            'default': default_val
        }
        
        if self.current_class_name and self.current_class_name in self.classes:
            self.classes[self.current_class_name]['properties'].append(prop_info)
        
        print(f"      Property: {prop_name} -> {prop_type}")
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_type_symbol(self):
        """Parse type symbol"""
        type_name = self.read_string()
        sym_id = self.read_longint()
        self._read_filepos()
        visibility = self.read_byte()
        sym_options = self._read_smallset()
        
        # Baca result type
        result_type = self._read_deref()
        
        # Baca pretty name (optional)
        if self.pos < self.current_entry_start + self.current_entry_size:
            pretty_name = self.read_ansistring()
        
        print(f"      Type: {type_name} -> {result_type}")
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_proc_symbol(self):
        """Parse procedure symbol"""
        proc_name = self.read_string()
        sym_id = self.read_longint()
        self._read_filepos()
        visibility = self.read_byte()
        sym_options = self._read_smallset()
        
        # Baca number of definitions
        def_count = self.read_word()
        
        for _ in range(def_count):
            definition = self._read_deref()
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_const_symbol(self):
        """Parse constant symbol"""
        const_name = self.read_string()
        sym_id = self.read_longint()
        self._read_filepos()
        visibility = self.read_byte()
        sym_options = self._read_smallset()
        
        # Baca const type
        const_type = self.read_byte()
        
        # Skip value based on type
        if const_type == 0:  # constord
            type_ref = self._read_deref()
            # Baca value (int64)
            self.read_byte()  # signed flag
            value = self.read_longint()
        elif const_type == 1:  # constpointer
            type_ref = self._read_deref()
            value = self.read_dword()
        elif const_type in [2, 3]:  # conststring, constresourcestring
            type_ref = self._read_deref()
            length = self.read_longint()
            string_val = self.data[self.pos:self.pos+length].decode('ascii', errors='replace')
            self.skip(length)
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_field_var_sym(self):
        """Parse field variable symbol (field dari class/record)"""
        field_name = self.read_string()
        sym_id = self.read_longint()
        self._read_filepos()
        visibility = self.read_byte()
        sym_options = self._read_smallset()
        
        # Baca var type
        self._read_deref()
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_implementation_section(self):
        """Parse implementation section"""
        print("\n📖 IMPLEMENTATION SECTION")
        print("-" * 50)
        
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDIMPLEMENTATION:
                print("   End of implementation section")
                break
            elif entry_id == EntryIdentifier.IBASMSYMBOLS:
                self._parse_asm_symbols()
            elif entry_id == EntryIdentifier.IBLOADUNIT:
                self._parse_load_unit()
            elif entry_id == EntryIdentifier.IBUNITIMPORTSYMS:
                self._parse_unit_import_syms()
            elif entry_id == 0 or entry_id == 255:
                break
            else:
                self.skip(self.current_entry_size)
    
    def _parse_asm_symbols(self):
        """Parse assembler symbols"""
        asm_type = self.read_byte()
        count = self.read_longint()
        print(f"   Asm symbols: {count} ({asm_type})")
        
        for _ in range(count):
            name = self.read_string()
            bind = self.read_byte()
            sym_type = self.read_byte()
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _parse_unit_import_syms(self):
        """Parse unit import symbols"""
        count = self.read_longint()
        print(f"   Imported symbols: {count}")
        
        for _ in range(count):
            self._read_deref()
        
        self.skip(self.current_entry_size - (self.pos - self.current_entry_start))
    
    def _read_smallset(self) -> set:
        """Baca smallset (byte yang merepresentasikan set)"""
        b = self.read_dword()
        result = set()
        for i in range(32):
            if b & (1 << i):
                result.add(i)
        return result
    
    def _read_filepos(self):
        """Baca file position info"""
        info = self.read_byte()
        
        # Parse fileindex
        idx_bits = info & 0x03
        if idx_bits == 0: self.read_byte()      # 1 byte
        elif idx_bits == 1: self.read_word()    # 2 bytes
        elif idx_bits == 2:                     # 3 bytes
            self.read_byte()
            self.read_word()
        else: self.read_dword()                  # 4 bytes
        
        # Parse line
        line_bits = (info >> 2) & 0x03
        if line_bits == 0: self.read_byte()
        elif line_bits == 1: self.read_word()
        elif line_bits == 2:
            self.read_byte()
            self.read_word()
        else: self.read_dword()
        
        # Parse column
        col_bits = (info >> 4) & 0x03
        if col_bits == 0: self.read_byte()
        elif col_bits == 1: self.read_word()
        elif col_bits == 2:
            self.read_byte()
            self.read_word()
        else: self.read_dword()
    
    def _read_deref(self, return_ref: bool = True) -> Optional[str]:
        """
        Baca dereference (referensi ke symbol/def lain)
        Format entry: longint offset ke deref_data, lalu deref_data berisi
        [len (byte)] [deref items...].
        """
        idx = self.read_longint()
        if idx == 0xFFFFFFFF:
            return None
        if self.deref_data is None or idx >= len(self.deref_data):
            return f"Deref({idx})"
        
        pos = idx
        length = self.deref_data[pos]
        pos += 1
        end = idx + 1 + length
        parts = []
        while pos < end and pos < len(self.deref_data):
            kind = self.deref_data[pos]
            pos += 1
            if kind == 0:
                parts.append("Nil")
            elif kind == 1:
                if pos + 4 > len(self.deref_data):
                    break
                ref_id = int.from_bytes(self.deref_data[pos:pos + 4], "big", signed=False)
                pos += 4
                parts.append(f"SymId {ref_id}")
            elif kind == 2:
                if pos + 4 > len(self.deref_data):
                    break
                ref_id = int.from_bytes(self.deref_data[pos:pos + 4], "big", signed=False)
                pos += 4
                parts.append(f"DefId {ref_id}")
            elif kind == 3:
                if pos + 2 > len(self.deref_data):
                    break
                unit_id = int.from_bytes(self.deref_data[pos:pos + 2], "big", signed=False)
                pos += 2
                unit_name = self.ref_units[unit_id] if unit_id < len(self.ref_units) else str(unit_id)
                parts.append(f"Unit {unit_name}")
            else:
                parts.append(f"DerefType({kind})")
                break
        return ", ".join(parts) if parts else f"Deref({idx})"
    
    def _read_prop_access_list(self, return_ref: bool = False) -> Optional[str]:
        """Baca property access list"""
        ref = self._read_deref()
        
        while True:
            sl_type = self.read_byte()
            if sl_type == 0:  # sl_none
                break
            elif sl_type in [1, 2, 3]:  # sl_call, sl_load, sl_subscript
                self._read_deref()
            elif sl_type in [5, 6]:  # sl_typeconv, sl_absolutetype
                self._read_deref()
            elif sl_type == 4:  # sl_vec
                self.read_longint()
                self._read_deref()
        
        return ref if return_ref else None
    
    def _skip_symtable(self):
        """Skip symtable (definitions dan symbols)"""
        # Skip symtable options
        self.read_byte()
        
        # Skip definitions
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDDEFS:
                break
            self.skip(self.current_entry_size)
        
        # Skip symbols
        while True:
            entry_id = self.read_entry()
            if entry_id == EntryIdentifier.IBENDSYMS:
                break
            self.skip(self.current_entry_size)
    
    def _object_type_to_str(self, obj_type: int) -> str:
        """Konversi object type ke string"""
        types = {
            0: "class",
            1: "object",
            2: "interfacecom",
            3: "interfacecorba",
            4: "cppclass",
            5: "dispinterface",
            6: "objcclass",
            7: "objcprotocol",
            8: "helper",
            9: "objccategory",
            10: "javaclass",
            11: "interfacejava"
        }
        return types.get(obj_type, f"unknown({obj_type})")
    
    def get_used_units(self) -> List[str]:
        """Dapatkan daftar unit yang digunakan"""
        return [u.name for u in self.used_units]
    
    def get_classes(self) -> Dict[str, Dict]:
        """Dapatkan semua class yang ditemukan"""
        return self.classes
    
    def get_published_properties(self) -> Dict[str, List[Dict]]:
        """Dapatkan semua published properties"""
        result = {}
        for class_name, class_info in self.classes.items():
            if class_info['properties']:
                result[class_name] = class_info['properties']
        return result
    
    def print_summary(self):
        """Print summary"""
        print("\n" + "=" * 60)
        print("PPU PARSING SUMMARY")
        print("=" * 60)
        
        print(f"\n📦 Unit: {self.unit_name}")
        
        print(f"\n📚 Used Units ({len(self.used_units)}):")
        for i, u in enumerate(self.used_units):
            print(f"   [{i}] {u.name}")
        
        print(f"\n🏛️ Classes ({len(self.classes)}):")
        for class_name, info in self.classes.items():
            prop_count = len(info['properties'])
            print(f"   📗 {class_name}: {info['obj_type']}, {prop_count} properties")
            for prop in info['properties']:
                print(f"      └─ {prop['name']}: {prop['type_ref']}")
        
        print("=" * 60)


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Parser Python eksperimental untuk file .ppu tanpa ppudump."
    )
    parser.add_argument("ppu_file", help="Path ke file .ppu")
    args = parser.parse_args()

    if not os.path.exists(args.ppu_file):
        print(f"File not found: {args.ppu_file}")
        sys.exit(1)

    reader = PPUFileReader(args.ppu_file)
    reader.parse()
    reader.print_summary()


if __name__ == "__main__":
    main()

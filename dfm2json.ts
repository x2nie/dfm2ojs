// dfmjson.ts
import { TParser, toSymbol, toString, toWString, toInteger, toFloat } from './tparser';
import * as fs from 'fs';

// Interface untuk JSON object yang akan kita gunakan
interface JSONValue {
    valueType?: string;
    asString?: string;
    asNumber?: number;
    asBoolean?: boolean;
    asInteger?: number;
    asFloat?: number;
}

class JSONObject {
    private data: Map<string, any> = new Map();

    constructor(init?: Record<string, any>) {
        if (init) {
            Object.entries(init).forEach(([key, value]) => {
                this.data.set(key, value);
            });
        }
    }

    addValue(key: string, value: any): void {
        this.data.set(key, value);
    }

    add(key: string, value: any): void {
        this.data.set(key, value);
    }

    get(key: string): any {
        return this.data.get(key);
    }

    getItems(key: string): any {
        return this.data.get(key);
    }

    getElementCount(): number {
        return this.data.size;
    }

    getNames(): string[] {
        return Array.from(this.data.keys());
    }

    getElements(): any[] {
        return Array.from(this.data.values());
    }

    toJSON(): Record<string, any> {
        const obj: Record<string, any> = {};
        this.data.forEach((value, key) => {
            obj[key] = value;
        });
        return obj;
    }

    isDefined(key: string): boolean {
        return this.data.has(key);
    }
}

class JSONArray {
    private items: any[] = [];

    constructor(init?: any[]) {
        if (init) {
            this.items = [...init];
        }
    }

    add(item: any): void {
        this.items.push(item);
    }

    addObject(): JSONObject {
        const obj = new JSONObject();
        this.items.push(obj);
        return obj;
    }

    getElementCount(): number {
        return this.items.length;
    }

    getElements(): any[] {
        return this.items;
    }

    [Symbol.iterator](): Iterator<any> {
        return this.items[Symbol.iterator]();
    }
}

class JSONImmediate {
    private value: any;
    valueType: string;

    constructor(value?: any) {
        this.value = value;
        this.valueType = 'immediate';
    }

    get asString(): string {
        return String(this.value);
    }

    set asString(value: string) {
        this.value = value;
    }

    get asInteger(): number {
        return Number(this.value);
    }

    set asInteger(value: number) {
        this.value = value;
    }

    get asBoolean(): boolean {
        return Boolean(this.value);
    }

    set asBoolean(value: boolean) {
        this.value = value;
    }

    get asNumber(): number {
        return Number(this.value);
    }

    toJSON(): any {
        return this.value;
    }
}

type TdwsJSONValue = JSONObject | JSONArray | JSONImmediate | string | number | boolean;
type TdwsJSONObject = JSONObject;
type TdwsJSONArray = JSONArray;
type TdwsJSONImmediate = JSONImmediate;

// Helper function untuk CharInSet
function CharInSet(ch: string, setStr: string): boolean {
    return setStr.includes(ch);
}

function ConvertOrderModifier(parser: TParser): number {
    if (parser.token === '[') {
        parser.nextToken();
        parser.checkToken(String.fromCharCode(3)); // toInteger
        const result = parser.tokenInt();
        parser.nextToken();
        parser.checkToken(']');
        parser.nextToken();
        return result;
    }
    return -1;
}

function ConvertHeader(parser: TParser, isInherited: boolean, isInline: boolean): TdwsJSONObject {
    parser.checkToken(String.fromCharCode(1)); // toSymbol
    let className = parser.tokenString();
    let objectName = '';
    
    if (parser.nextToken() === ':') {
        parser.nextToken();
        parser.checkToken(String.fromCharCode(1)); // toSymbol
        objectName = className;
        className = parser.tokenString();
        parser.nextToken();
    }
    
    const position = ConvertOrderModifier(parser);
    const result = new JSONObject();
    
    if (isInherited) {
        result.addValue('$Inherited', true);
    }
    if (isInline) {
        result.addValue('$Inline', true);
    }
    if (position >= 0) {
        result.addValue('$ChildPos', position);
    }
    result.addValue('$Class', className);
    if (objectName !== '') {
        result.addValue('$Name', objectName);
    }
    
    return result;
}

function ConvertValue(parser: TParser): TdwsJSONValue {
    const CombineString = (): string => {
        let result = parser.tokenWideString();
        while (parser.nextToken() === '+') {
            parser.nextToken();
            const tokenCode = parser.token.charCodeAt(0);
            if (!CharInSet(parser.token, String.fromCharCode(toString) + String.fromCharCode(toWString))) {
                parser.checkToken(String.fromCharCode(toString));
            }
            result += parser.tokenWideString();
        }
        return result;
    };

    const tokenCode = parser.token.charCodeAt(0);
    
    if (CharInSet(parser.token, String.fromCharCode(toString) + String.fromCharCode(toWString))) {
        const result = new JSONImmediate();
        result.asString = `"${CombineString()}"`;
        return result;
    } else {
        switch (parser.token) {
            case String.fromCharCode(1): { // toSymbol
                const tokenStr = parser.tokenComponentIdent();
                const result = new JSONImmediate();
                if (tokenStr === 'True') {
                    result.asBoolean = true;
                } else if (tokenStr === 'False') {
                    result.asBoolean = false;
                } else {
                    result.asString = parser.tokenComponentIdent();
                }
                parser.nextToken();
                return result;
            }
            case String.fromCharCode(3): { // toInteger
                const result = new JSONImmediate();
                result.asInteger = parser.tokenInt();
                parser.nextToken();
                return result;
            }
            case String.fromCharCode(4): { // toFloat
                const result = new JSONObject();
                if (parser.floatType === '') {
                    const nullValue = new JSONImmediate(null);
                    result.add('$float', nullValue);
                } else {
                    result.addValue('$float', parser.floatType);
                }
                result.addValue('value', parser.tokenFloat());
                parser.nextToken();
                return result;
            }
            case '[': { // SET
                const result = new JSONObject();
                result.addValue('$set', true);
                const arr = new JSONArray();
                result.addValue('value', arr);
                parser.nextToken();
                
                if (parser.token !== ']') {
                    while (true) {
                        let tokenStr = parser.tokenString();
                        const token = parser.token;
                        if (token === String.fromCharCode(3)) { // toInteger
                            // do nothing
                        } else if (token === String.fromCharCode(toString) || token === String.fromCharCode(toWString)) {
                            tokenStr = '#' + tokenStr.charCodeAt(0);
                        } else {
                            parser.checkToken(String.fromCharCode(1)); // toSymbol
                        }
                        arr.add(tokenStr);
                        if (parser.nextToken() === ']') break;
                        parser.checkToken(',');
                        parser.nextToken();
                    }
                }
                parser.nextToken();
                return result;
            }
            case '(': { // LIST
                parser.nextToken();
                const result = new JSONArray();
                while (parser.token !== ')') {
                    result.add(ConvertValue(parser));
                }
                parser.nextToken();
                return result;
            }
            case '{': { // BINARY
                parser.nextToken();
                const result = new JSONObject();
                result.addValue('$hex', true);
                let tokenStr = '';
                while (parser.token !== '}') {
                    tokenStr += parser.tokenString();
                    parser.nextToken();
                }
                result.addValue('value', tokenStr);
                parser.nextToken();
                return result;
            }
            case '<': { // COLLECTION
                parser.nextToken();
                const result = new JSONObject();
                result.addValue('$collection', true);
                const arr = new JSONArray();
                result.addValue('values', arr);
                
                while (parser.token !== '>') {
                    parser.checkTokenSymbol('item');
                    parser.nextToken();
                    const order = ConvertOrderModifier(parser);
                    const sub = arr.addObject();
                    if (order !== -1) {
                        sub.addValue('$order', order);
                    }
                    while (!parser.tokenSymbolIs('end')) {
                        ConvertProperty(parser, sub);
                    }
                    parser.nextToken();
                }
                parser.nextToken();
                return result;
            }
            default:
                parser.error('Invalid property');
                return new JSONImmediate(null);
        }
    }
}

function ConvertProperty(parser: TParser, obj: TdwsJSONObject): void {
    parser.checkToken(String.fromCharCode(1)); // toSymbol
    let propName = parser.tokenString();
    parser.nextToken();
    
    while (parser.token === '.') {
        parser.nextToken();
        parser.checkToken(String.fromCharCode(1)); // toSymbol
        propName += '.' + parser.tokenString();
        parser.nextToken();
    }
    
    parser.checkToken('=');
    parser.nextToken();
    obj.add(propName, ConvertValue(parser));
}

function ConvertObject(parser: TParser): TdwsJSONObject {
    let inheritedObject = false;
    let inlineObject = false;
    
    if (parser.tokenSymbolIs('INHERITED')) {
        inheritedObject = true;
    } else if (parser.tokenSymbolIs('INLINE')) {
        inlineObject = true;
    } else {
        parser.checkTokenSymbol('OBJECT');
    }
    
    parser.nextToken();
    const result = ConvertHeader(parser, inheritedObject, inlineObject);
    
    while (!parser.tokenSymbolIs('END') &&
           !parser.tokenSymbolIs('OBJECT') &&
           !parser.tokenSymbolIs('INHERITED') &&
           !parser.tokenSymbolIs('INLINE')) {
        ConvertProperty(parser, result);
    }
    
    const children = new JSONArray();
    result.addValue('$Children', children);
    
    while (!parser.tokenSymbolIs('END')) {
        children.add(ConvertObject(parser));
    }
    
    parser.nextToken();
    return result;
}

export function Dfm2JSON(dfm: Buffer | NodeJS.ReadableStream): TdwsJSONObject {
    // Create a simple stream interface for Buffer
    const stream = {
        buffer: Buffer.isBuffer(dfm) ? dfm : Buffer.from(''),
        position: 0,
        read(buffer: Buffer, size: number): number {
            const bytesToRead = Math.min(size, this.buffer.length - this.position);
            this.buffer.copy(buffer, 0, this.position, this.position + bytesToRead);
            this.position += bytesToRead;
            return bytesToRead;
        }
    };
    
    const parser = new TParser(stream);
    try {
        return ConvertObject(parser);
    } finally {
        // parser cleanup handled by GC
    }
}

export function Dfm2JSONFromFile(filename: string): TdwsJSONObject {
    const content = fs.readFileSync(filename);
    return Dfm2JSON(content);
}

export function DfmBin2JSON(dfm: Buffer): TdwsJSONObject {
    // Convert binary DFM to text format first
    // This is a simplification - in real implementation you'd need to parse binary DFM
    const text = dfm.toString('utf-8');
    return Dfm2JSON(Buffer.from(text));
}

export function DfmBin2JSONFromFile(filename: string): TdwsJSONObject {
    const content = fs.readFileSync(filename);
    return DfmBin2JSON(content);
}

// Helper functions for JSON to DFM conversion
function IndentStr(depth: number): string {
    return ' '.repeat(depth * 2);
}

function capitalize(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}

function StringNeedsWork(str: string): boolean {
    return str.length > 66 || str.includes('\r') || str.includes('\n');
}

function DfmQuotedStr(value: string): string {
    const separators = ['\r\n', '\r', '\n'];
    const lines = value.split(new RegExp(separators.join('|'), 'g'));
    const quoted = lines.map(line => line !== '' ? `"${line}"` : '');
    return quoted.join('#13');
}

// function WriteJSONProperty(name: string, value: any, sl: string[], indent: number): void;
// function WriteJSONObject(json: TdwsJSONObject, sl: string[], indent: number): void;

function WriteJSONProperty(name: string, value: any, sl: string[], indent: number): void {
    if (value && typeof value === 'object') {
        if (value.valueType === 'immediate' || value.asString !== undefined) {
            // Handle immediate values
            let str = value.asString || String(value);
            if (str.startsWith('"') && StringNeedsWork(str)) {
                str = str.slice(1, -1); // Remove quotes
                sl.push(IndentStr(indent) + `${name} = `);
                while (str.length > 0) {
                    let sub = DfmQuotedStr(str.slice(0, 64));
                    str = str.slice(64);
                    if (str !== '') {
                        sub += ' +';
                    }
                    sl.push(IndentStr(indent + 1) + sub);
                }
            } else {
                sl.push(IndentStr(indent) + `${name} = ${str}`);
            }
        } else if (value.get && value.get('$float') !== undefined) {
            // Handle float
            const floatVal = value.get('value');
            const num = floatVal;
            let numVal: string;
            if (Number.isInteger(num) && !num.toString().includes('e')) {
                numVal = num.toString() + '.000000000000000000';
            } else {
                numVal = num.toString();
            }
            const floatType = value.get('$float');
            if (floatType && floatType.valueType !== 'immediate') {
                sl.push(IndentStr(indent) + `${name} = ${numVal}${floatType}`);
            } else {
                sl.push(IndentStr(indent) + `${name} = ${numVal}`);
            }
        } else if (value.get && value.get('$set') !== undefined) {
            // Handle set
            const sub = value.get('value');
            const items: string[] = [];
            for (const item of sub.getElements()) {
                items.push(item);
            }
            sl.push(IndentStr(indent) + `${name} = [${items.join(', ')}]`);
        } else if (value.get && value.get('$hex') !== undefined) {
            // Handle hex binary
            sl.push(IndentStr(indent) + `${name} = {`);
            let hex = value.get('value');
            while (hex.length > 0) {
                let line = hex.slice(0, 64);
                hex = hex.slice(64);
                if (hex.length === 0) {
                    line += '}';
                }
                sl.push(IndentStr(indent + 1) + line);
            }
        } else if (value.get && value.get('$collection') !== undefined) {
            // Handle collection
            sl.push(IndentStr(indent) + `${name} = <`);
            const values = value.get('values');
            for (const sub of values.getElements()) {
                if (sub.get('$order') !== undefined) {
                    sl.push(IndentStr(indent + 1) + `item [${sub.get('$order')}]`);
                } else {
                    sl.push(IndentStr(indent + 1) + 'item');
                }
                for (let i = 0; i < sub.getElementCount(); i++) {
                    const propName = sub.getNames()[i];
                    if (!propName.startsWith('$')) {
                        WriteJSONProperty(propName, sub.get(propName), sl, indent + 2);
                    }
                }
                sl.push(IndentStr(indent + 1) + 'end');
            }
            sl[sl.length - 1] = sl[sl.length - 1] + '>';
        } else if (value.getElements) {
            // Handle array
            sl.push(IndentStr(indent) + `${name} = (`);
            for (let i = 0; i < value.getElementCount(); i++) {
                let line = IndentStr(indent + 1) + String(value.getElements()[i]);
                if (i === value.getElementCount() - 1) {
                    line += ')';
                }
                sl.push(line);
            }
        } else {
            // Handle nested object
            WriteJSONObject(value, sl, indent);
        }
    } else {
        // Handle primitive values
        if (typeof value === 'string') {
            sl.push(IndentStr(indent) + `${name} = "${value}"`);
        } else if (typeof value === 'number') {
            sl.push(IndentStr(indent) + `${name} = ${value}`);
        } else if (typeof value === 'boolean') {
            sl.push(IndentStr(indent) + `${name} = ${capitalize(String(value))}`);
        }
    }
}

function WriteJSONObject(json: TdwsJSONObject, sl: string[], indent: number): void {
    let dfmType: string;
    if (json.isDefined('$Inherited')) {
        dfmType = 'inherited';
    } else if (json.isDefined('$Inline')) {
        dfmType = 'inline';
    } else {
        dfmType = 'object';
    }
    
    const name = json.isDefined('$Name') ? json.get('$Name') : '';
    const cls = json.get('$Class');
    
    let header: string;
    if (name === '') {
        header = `${dfmType} ${cls}`;
    } else {
        header = `${dfmType} ${name}: ${cls}`;
    }
    
    if (json.isDefined('$ChildPos')) {
        header = `${header} [${json.get('$ChildPos')}]`;
    }
    
    sl.push(IndentStr(indent) + header);
    
    // Write properties
    for (let i = 0; i < json.getElementCount(); i++) {
        const propName = json.getNames()[i];
        if (!propName.startsWith('$')) {
            WriteJSONProperty(propName, json.get(propName), sl, indent + 1);
        }
    }
    
    // Write children
    const children = json.get('$Children');
    if (children && children.getElements) {
        for (const child of children.getElements()) {
            WriteJSONObject(child, sl, indent + 1);
        }
    }
    
    sl.push(IndentStr(indent) + 'end');
}

export function JSON2Dfm(json: TdwsJSONObject): string {
    const sl: string[] = [];
    WriteJSONObject(json, sl, 0);
    return sl.join('\n');
}

export function SaveJSON2Dfm(json: TdwsJSONObject, filename: string): void {
    fs.writeFileSync(filename, JSON2Dfm(json));
}

// Additional helper to parse JSON string to JSONObject
export function parseJSONToObject(jsonStr: string): TdwsJSONObject {
    const parsed = JSON.parse(jsonStr);
    const result = new JSONObject();
    
    function convert(obj: any): any {
        if (Array.isArray(obj)) {
            const arr = new JSONArray();
            obj.forEach(item => arr.add(convert(item)));
            return arr;
        } else if (obj && typeof obj === 'object') {
            const newObj = new JSONObject();
            Object.entries(obj).forEach(([key, value]) => {
                newObj.addValue(key, convert(value));
            });
            return newObj;
        }
        return obj;
    }
    
    Object.entries(parsed).forEach(([key, value]) => {
        result.addValue(key, convert(value));
    });
    
    return result;
}
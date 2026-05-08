//consider to learn: https://github.com/jean-lopes/dfm-to-json/tree/master


// Constants
const ParseBufSize = 4096; // Modern systems can handle this
const LastSpecialToken = 5;

const TokNames: string[] = [
    'EOF',
    'Symbol',
    'String',
    'Integer',
    'Float',
    'WideString'
];

// Custom error class
class EParserError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'EParserError';
    }
}

// Stream interface (simplified for TypeScript)
interface TStream {
    read(buffer: Buffer, size: number): number;
    position: number;
}

// Main Parser class
class TParser {
    private fStream: TStream;
    private fBuf: Buffer;
    private fBufLen: number;
    private fPos: number;
    private fDeltaPos: number;
    private fFloatType: string;
    private fSourceLine: number;
    private fToken: string;
    private fEofReached: boolean;
    private fLastTokenStr: string;
    private fLastTokenWStr: string;

    constructor(stream: TStream) {
        this.fStream = stream;
        this.fBuf = Buffer.alloc(ParseBufSize + 1);
        this.fBufLen = 0;
        this.fPos = 0;
        this.fDeltaPos = 1;
        this.fSourceLine = 1;
        this.fEofReached = false;
        this.fLastTokenStr = '';
        this.fLastTokenWStr = '';
        this.fFloatType = '';
        this.fToken = '';
        
        this.loadBuffer();
        this.skipBOM();
        this.nextToken();
    }

    private getTokenName(aTok: string): string {
        const code = aTok.charCodeAt(0);
        if (code <= LastSpecialToken) {
            return TokNames[code];
        }
        return aTok;
    }

    private loadBuffer(): void {
        const bytesRead = this.fStream.read(this.fBuf, ParseBufSize);
        this.fBuf[bytesRead] = 0;
        this.fDeltaPos += bytesRead;
        this.fPos = 0;
        this.fBufLen = bytesRead;
        this.fEofReached = bytesRead === 0;
    }

    private checkLoadBuffer(): void {
        if (this.fBuf[this.fPos] === 0) {
            this.loadBuffer();
        }
    }

    private processChar(): void {
        this.fLastTokenStr += String.fromCharCode(this.fBuf[this.fPos]);
        this.fPos++;
        this.checkLoadBuffer();
    }

    private isNumber(): boolean {
        const ch = this.fBuf[this.fPos];
        return ch >= 48 && ch <= 57; // '0' - '9'
    }

    private isHexNum(): boolean {
        const ch = this.fBuf[this.fPos];
        return (ch >= 48 && ch <= 57) || // 0-9
               (ch >= 65 && ch <= 70) || // A-F
               (ch >= 97 && ch <= 102);  // a-f
    }

    private isAlpha(): boolean {
        const ch = this.fBuf[this.fPos];
        return ch === 95 || // _
               (ch >= 65 && ch <= 90) || // A-Z
               (ch >= 97 && ch <= 122);  // a-z
    }

    private isAlphaNum(): boolean {
        return this.isAlpha() || this.isNumber();
    }

    private getHexValue(c: number): number {
        if (c >= 48 && c <= 57) return c - 48;      // '0'-'9'
        if (c >= 65 && c <= 70) return c - 55;      // 'A'-'F' (65-55=10)
        if (c >= 97 && c <= 102) return c - 87;     // 'a'-'f' (97-87=10)
        return 0;
    }

    private getAlphaNum(): string {
        if (!this.isAlpha()) {
            this.errorFmt('Expected', [this.getTokenName('Symbol')]);
        }
        let result = '';
        while (this.isAlphaNum()) {
            result += String.fromCharCode(this.fBuf[this.fPos]);
            this.fPos++;
            this.checkLoadBuffer();
        }
        return result;
    }

    private handleNewLine(): void {
        if (this.fBuf[this.fPos] === 13) { // CR
            this.fPos++;
            this.checkLoadBuffer();
        }
        if (this.fBuf[this.fPos] === 10) { // LF
            this.fPos++;
            this.checkLoadBuffer();
        }
        this.fSourceLine++;
        this.fDeltaPos = -(this.fPos - 1);
    }

    private skipBOM(): void {
        const backup = this.fPos;
        let bom = '';
        
        for (let i = 0; i < 3; i++) {
            const ch = this.fBuf[this.fPos];
            if (ch === 0xBB || ch === 0xBF || ch === 0xEF) {
                bom += String.fromCharCode(ch);
                this.fPos++;
                this.checkLoadBuffer();
            } else {
                break;
            }
        }
        
        if (bom !== '\u00EF\u00BB\u00BF') {
            this.fPos = backup;
        }
    }

    private skipSpaces(): void {
        while (this.fBuf[this.fPos] === 32 || this.fBuf[this.fPos] === 9) { // space or tab
            this.fPos++;
            this.checkLoadBuffer();
        }
    }

    private skipWhitespace(): void {
        while (true) {
            const ch = this.fBuf[this.fPos];
            if (ch === 32 || ch === 9) {
                this.skipSpaces();
            } else if (ch === 10 || ch === 13) {
                this.handleNewLine();
            } else {
                break;
            }
        }
    }

    private handleEof(): void {
        this.fToken = String.fromCharCode(0); // EOF
        this.fLastTokenStr = '';
    }

    private handleAlphaNum(): void {
        this.fLastTokenStr = this.getAlphaNum();
        this.fToken = String.fromCharCode(1); // Symbol
    }

    private handleNumber(): void {
        this.fLastTokenStr = '';
        while (this.isNumber()) {
            this.processChar();
        }
        this.fToken = String.fromCharCode(3); // Integer
        
        const ch = String.fromCharCode(this.fBuf[this.fPos]);
        if (ch === '.' || ch === 'e' || ch === 'E') {
            this.fToken = String.fromCharCode(4); // Float
            let allowedDot = true;
            let allowedE = true;
            
            while (true) {
                const currentCh = String.fromCharCode(this.fBuf[this.fPos]);
                if (currentCh === '.' && allowedDot) {
                    allowedDot = false;
                    this.processChar();
                } else if ((currentCh === 'e' || currentCh === 'E') && allowedE) {
                    allowedE = false;
                    this.processChar();
                    const nextCh = String.fromCharCode(this.fBuf[this.fPos]);
                    if (nextCh === '+' || nextCh === '-') {
                        this.processChar();
                    }
                    if (!this.isNumber()) {
                        this.errorFmt('Invalid float', [this.fLastTokenStr + String.fromCharCode(this.fBuf[this.fPos])]);
                    }
                    this.processChar();
                } else if (this.isNumber()) {
                    this.processChar();
                } else {
                    break;
                }
            }
        }
        
        const currentCh = String.fromCharCode(this.fBuf[this.fPos]);
        if (['s', 'S', 'd', 'D', 'c', 'C'].includes(currentCh)) {
            this.fFloatType = currentCh;
            this.fPos++;
            this.checkLoadBuffer();
            this.fToken = String.fromCharCode(4); // Float
        } else {
            this.fFloatType = '';
        }
    }

    private handleHexNumber(): void {
        this.fLastTokenStr = '$';
        this.fPos++;
        this.checkLoadBuffer();
        let valid = false;
        
        while (this.isHexNum()) {
            valid = true;
            this.processChar();
        }
        
        if (!valid) {
            this.errorFmt('Invalid integer', [this.fLastTokenStr]);
        }
        this.fToken = String.fromCharCode(3); // Integer
    }

    private handleQuotedString(): string {
        let result = '';
        this.fPos++;
        this.checkLoadBuffer();
        
        while (true) {
            const ch = this.fBuf[this.fPos];
            if (ch === 0) {
                this.errorStr('Unterminated string');
            } else if (ch === 13 || ch === 10) {
                this.errorStr('Unterminated string');
            } else if (ch === 39) { // '
                this.fPos++;
                this.checkLoadBuffer();
                if (this.fBuf[this.fPos] !== 39) {
                    return result;
                }
            } else {
                result += String.fromCharCode(ch);
                this.fPos++;
                this.checkLoadBuffer();
            }
        }
    }

    private handleDecimalCharacter(): { ascii: boolean; wideChr: string; stringChr: string } {
        this.fPos++;
        this.checkLoadBuffer();
        
        let i = 0;
        while (this.isNumber() && i < 65535) {
            i = i * 10 + (this.fBuf[this.fPos] - 48);
            this.fPos++;
            this.checkLoadBuffer();
        }
        
        if (i > 65535) i = 0;
        const ascii = i <= 127;
        const wideChr = String.fromCharCode(i);
        const stringChr = i < 256 ? String.fromCharCode(i) : '';
        
        return { ascii, wideChr, stringChr };
    }

    private handleString(): void {
        this.fLastTokenWStr = '';
        this.fLastTokenStr = '';
        let ascii = true;
        
        while (true) {
            const ch = this.fBuf[this.fPos];
            if (ch === 39) { // '
                const s = this.handleQuotedString();
                this.fLastTokenWStr += s;
                this.fLastTokenStr += s;
            } else if (ch === 35) { // #
                const { ascii: isAscii, wideChr, stringChr } = this.handleDecimalCharacter();
                ascii = ascii && isAscii;
                this.fLastTokenWStr += wideChr;
                this.fLastTokenStr += stringChr;
            } else {
                break;
            }
        }
        
        this.fToken = ascii ? String.fromCharCode(2) : String.fromCharCode(5); // String or WideString
    }

    private handleMinus(): void {
        this.fPos++;
        this.checkLoadBuffer();
        
        if (this.isNumber()) {
            this.handleNumber();
            this.fLastTokenStr = '-' + this.fLastTokenStr;
        } else {
            this.fToken = '-';
            this.fLastTokenStr = this.fToken;
        }
    }

    private handleUnknown(): void {
        this.fToken = String.fromCharCode(this.fBuf[this.fPos]);
        this.fLastTokenStr = this.fToken;
        this.fPos++;
        this.checkLoadBuffer();
    }

    // Public methods
    checkToken(T: string): void {
        if (this.fToken !== T) {
            this.errorFmt('Wrong token type', [this.getTokenName(T), this.getTokenName(this.fToken)]);
        }
    }

    checkTokenSymbol(S: string): void {
        this.checkToken(String.fromCharCode(1)); // Symbol
        if (this.fLastTokenStr.toLowerCase() !== S.toLowerCase()) {
            this.errorFmt('Wrong token symbol', [S, this.fLastTokenStr]);
        }
    }

    error(ident: string): void {
        this.errorStr(ident);
    }

    errorFmt(ident: string, args: any[]): void {
        // Simple format replacement - in real implementation use a proper formatter
        let message = ident;
        args.forEach((arg, idx) => {
            message = message.replace(`%${idx}`, arg);
        });
        this.errorStr(message);
    }

    errorStr(message: string): void {
        const lineInfo = ` at line ${this.fSourceLine}, pos ${this.fPos + this.fDeltaPos}`;
        throw new EParserError(message + lineInfo);
    }

    hexToBinary(stream: TStream): void {
        const outbuf = Buffer.alloc(ParseBufSize);
        let i = 0;
        
        this.skipWhitespace();
        while (this.isHexNum()) {
            let b = this.getHexValue(this.fBuf[this.fPos]) << 4;
            this.fPos++;
            this.checkLoadBuffer();
            
            if (!this.isHexNum()) {
                this.error('Unterminated binary value');
            }
            b |= this.getHexValue(this.fBuf[this.fPos]);
            this.fPos++;
            this.checkLoadBuffer();
            
            outbuf[i] = b;
            i++;
            
            if (i >= ParseBufSize) {
                stream.write(outbuf.subarray(0, i));
                i = 0;
            }
            this.skipWhitespace();
        }
        
        if (i > 0) {
            stream.write(outbuf.subarray(0, i));
        }
        this.nextToken();
    }

    nextToken(): string {
        this.skipWhitespace();
        
        if (this.fEofReached) {
            this.handleEof();
        } else {
            const ch = this.fBuf[this.fPos];
            const chStr = String.fromCharCode(ch);
            
            if (this.isAlpha()) {
                this.handleAlphaNum();
            } else if (chStr === '$') {
                this.handleHexNumber();
            } else if (chStr === '-') {
                this.handleMinus();
            } else if (this.isNumber()) {
                this.handleNumber();
            } else if (chStr === "'" || chStr === '#') {
                this.handleString();
            } else {
                this.handleUnknown();
            }
        }
        
        return this.fToken;
    }

    sourcePos(): number {
        return this.fStream.position - this.fBufLen + this.fPos;
    }

    tokenComponentIdent(): string {
        if (this.fToken !== String.fromCharCode(1)) {
            this.errorFmt('Expected', [this.getTokenName(String.fromCharCode(1))]);
        }
        
        this.checkLoadBuffer();
        while (String.fromCharCode(this.fBuf[this.fPos]) === '.') {
            this.processChar();
            this.fLastTokenStr += this.getAlphaNum();
        }
        
        return this.fLastTokenStr;
    }

    tokenFloat(): number {
        const value = parseFloat(this.fLastTokenStr);
        if (isNaN(value)) {
            this.errorFmt('Invalid float', [this.fLastTokenStr]);
        }
        return value;
    }

    tokenInt(): number {
        const value = parseInt(this.fLastTokenStr, 10);
        if (isNaN(value)) {
            // Second chance for malformed files
            return parseInt(this.fLastTokenStr, 16);
        }
        return value;
    }

    tokenString(): string {
        const tokenCode = this.fToken.charCodeAt(0);
        if (tokenCode === 5) { // WideString
            return this.fLastTokenWStr;
        } else if (tokenCode === 4 && this.fFloatType !== '') { // Float
            return this.fLastTokenStr + this.fFloatType;
        } else {
            return this.fLastTokenStr;
        }
    }

    tokenWideString(): string {
        if (this.fToken.charCodeAt(0) === 5) { // WideString
            return this.fLastTokenWStr;
        } else {
            return this.fLastTokenStr;
        }
    }

    tokenSymbolIs(S: string): boolean {
        return this.fToken.charCodeAt(0) === 1 && // Symbol
               this.fLastTokenStr.toLowerCase() === S.toLowerCase();
    }

    // Getters
    get floatType(): string {
        return this.fFloatType;
    }

    get sourceLine(): number {
        return this.fSourceLine;
    }

    get token(): string {
        return this.fToken;
    }
}

// Note: Some functionality like stream write operations may need to be
// implemented based on your specific environment (Node.js, browser, etc.)
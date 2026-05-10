class TCollectionItem {
    // collection: TCollection | null = null;
    // [key: string]: any;
}

class TCollection extends Array/* <TCollectionItem> */ {

}

class TSymbol extends String {};
export class TSymbols extends Array {};

class TSet extends Set/* <string>  */{}

function symbols(values) {
    values = Array.from(arguments)
    // return values.map((v) => new TSymbol(v));
    return new TSymbols(...values)
}

function property(type, defaultValue) {
    return { type, defaultValue }; //? String, Boolean = lost on json.stringify!
    return { 
        // type: typeof type === 'function' ? type.name : type,
        type: type.name,
        defaultValue 
    };
}

function setOf(values) {
    return new TSet(values);
}

export {
    symbols,
    setOf as set_of,
    property,
}

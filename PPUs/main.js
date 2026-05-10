
import { TSymbols } from "./runtime.js";
async function main() {
    const res = window.res = await import("./unit1.js");
    for(const [name, value] of Object.entries(res)) {
        //console.log(name, value);
        if(value instanceof TSymbols){
            value.name = name
        }
    }
    console.log(res)
}

main();
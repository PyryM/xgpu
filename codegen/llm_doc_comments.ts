import { readFileSync } from "fs";

const src = readFileSync("webgoo/bindings.py").toString("utf8");
let curClass: string | undefined = undefined;

for(const line of src.split("\n")) {
  if(line.startsWith("class ")) {
    const matched = line.trim().match(/^class ([^(]*)(?:\([^)]*\))?:/);
    if(!matched) {
      console.log("Missing match?", line);
      continue
    }
    const [_match, className] = matched;
    curClass = className;
  } else {
    const matched = line.match(/^(\s*)def ([^(]+)\(/);
    if(!matched) {continue}
    const [_match, indent, funcname] = matched;
    if(indent.length == 0) {
      curClass = undefined;
    }
    if(curClass?.startsWith("_") || funcname.startsWith("_")) {
      continue;
    }
    const name = curClass === undefined ? funcname : `${curClass}.${funcname}`;
    console.log("Found:", name);
  }
}
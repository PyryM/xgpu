import { readFileSync } from "fs";

const src = readFileSync("webgoo/bindings.py").toString("utf8");
let curClass: string | undefined = undefined;

let nextFuncIsProperty = false;

interface DocThing {
  parent?: string;
  name: string;
  kind: "class" | "func" | "prop";
}

const things: Map<string, DocThing> = new Map();

for (const line of src.split("\n")) {
  if (line.startsWith("class ")) {
    const matched = line.trim().match(/^class ([^(]*)(?:\([^)]*\))?:/);
    if (!matched) {
      console.log("Missing match?", line);
      continue;
    }
    const [_match, className] = matched;
    curClass = className;
    if (!things.has(className)) {
      things.set(className, { name: className, kind: "class" });
    }
  } else if (line.trim().startsWith("@property")) {
    nextFuncIsProperty = true;
  } else {
    const matched = line.match(/^(\s*)def ([^(]+)\(/);
    if (!matched) {
      continue;
    }
    const [_match, indent, funcname] = matched;
    const isProp = nextFuncIsProperty;
    nextFuncIsProperty = false;
    if (indent.length == 0) {
      curClass = undefined;
    }
    if (curClass?.startsWith("_") || funcname.startsWith("_")) {
      continue;
    }
    const name = curClass === undefined ? funcname : `${curClass}.${funcname}`;
    if (!things.has(name)) {
      things.set(name, {
        kind: isProp ? "prop" : "func",
        parent: curClass,
        name: funcname,
      });
    }
  }
}

for (const [name, thing] of things.entries()) {
  console.log(name, "->", thing.name, thing.kind);
}

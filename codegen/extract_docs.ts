import { readFileSync, writeFileSync } from "fs";

interface Section {
  name: string;
  indent: number;
  linkName: string;
  content: string[];
};

interface DictEntry {
  required?: boolean;
  defaultVal?: string;
  name: string;
  type: string;
}

interface IDL {
  content: string[]
  name?: string
  dictionary?: Map<string, DictEntry>
}

function parseEntry(line: string): DictEntry | undefined {
  line = line.trim();
  if(line.length === 0) {
    return undefined
  }
  const [prefix, defaultVal] = line.split(/\s*=\s*/);
  const parts = prefix.split(/\s+/);
  return {
    name: parts[parts.length-1],
    type: parts[parts.length-2],
    defaultVal,
    required: parts[0].trim() === "required"
  }
}

function parseIDL(lines: string[]): IDL {
  const firstLine = lines[0] ?? "";
  const dictMatch = firstLine.match(/^dictionary ([A-Za-z0-9]+)/);
  if(!dictMatch) {
    return {content: lines}
  }
  const name = dictMatch[1].trim();
  const dictionary: Map<string, DictEntry> = new Map();
  const body = (lines.join("")).match(/\{(.*)\};/);
  if(!body) {
    return {content: lines}
  }
  for(const line of body[1].split(";")) {
    const entry = parseEntry(line);
    if(entry) {
      dictionary.set(entry.name, entry);
    }
  }
  return { content: lines, name, dictionary};
}

class DocMap {
  sections: Map<string, Section> = new Map();
  srcLines: string[];
  idls: IDL[] = [];
  dictIdls: Map<string, IDL> = new Map();

  constructor(public src: string) {
    this.srcLines = src.split("\n").map((s) => s.trim());
    this._findSections();
    this._findIDLs();
  }

  search(query: string): Section[] {
    const matches: Section[] = [];
    for (const section of this.sections.values()) {
      if (section.content.find((line) => line.includes(query))) {
        matches.push(section);
      }
    }
    return matches;
  }

  _findIDLs() {
    let current: string[] | undefined = undefined;
    for (const line of this.srcLines) {
      if (current === undefined) {
        //ex: "### QuerySet Destruction ### {#queryset-destruction}"
        if (line === "<script type=idl>") {
          current = [];
        }
      } else {
        if (line === "</script>") {
          const idl = parseIDL(current);
          this.idls.push(idl);
          if (idl.name && idl.dictionary) {
            this.dictIdls.set(idl.name, idl);
          }
          current = undefined;
        } else {
          current.push(line);
        }
      }
    }
  }

  findDictDefault(dictName: string, fieldName: string): string | undefined {
    const altName = dictName.replaceAll("WGPU", "GPU");
    const dict = this.dictIdls.get(dictName) ?? this.dictIdls.get(altName);
    if(dict === undefined) {
      return undefined;
    }
    return dict?.dictionary?.get(fieldName)?.defaultVal;
  }

  _findSections() {
    let current: Section | undefined;
    for (const line of this.srcLines) {
      //ex: "### QuerySet Destruction ### {#queryset-destruction}"
      const match = line.match(/^(#+)([^#]*)(#+)\s*{(.*)}$/i);
      if (match) {
        const [, hashes, name, , linkName] = match;
        current = { name, indent: hashes.length, linkName, content: [] };
        this.sections.set(linkName, current);
      } else {
        current?.content.push(line);
      }
    }
  }
}

const SRC = readFileSync("codegen/webgpu_spec.bs").toString("utf8");
export const docs = new DocMap(SRC);

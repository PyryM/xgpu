import { readFileSync } from "fs";

type Section = {
  name: string;
  indent: number;
  linkName: string;
  content: string[];
};

class DocMap {
  sections: Map<string, Section> = new Map();

  constructor(public src: string) {
    this._findSections(src);
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

  _findSections(src: string) {
    let current: Section | undefined;
    for (const line of src.split("\n")) {
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
const docs = new DocMap(SRC);
for (const [link, section] of docs.sections.entries()) {
  console.log(link, "=>", section.name, section.content.length);
}
const occ = docs.sections.get("#gpu-interface");
if (occ) {
  console.log(occ.content);
}

for (const sec of docs.search("requestAdapter")) {
  console.log(`${sec.linkName}: "${sec.name}"`);
}

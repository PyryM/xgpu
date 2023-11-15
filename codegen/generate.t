local TAB = (" "):rep(4)

local function emit_enum(name, vals)
  local frags = {("class %s(IntEnum):"):format(name)}
  for _, valpair in ipairs(vals) do
    local name, val = unpack(valpair)
    table.insert(frags, TAB .. ("%s = %d"):format(name, val))
  end
  return table.concat(frags, "\n")
end

local function inget(t, k, default)
  if not t[k] then t[k] = default end
  return t[k]
end

local function gather_enums(header)
  local enums = {}
  for k, v in pairs(header) do
    if type(v) == 'number' then
      local enum_name, val_name = k:match("^WGPU([^_]*)_(.*)")
      if enum_name and enum_name ~= "" then
        if val_name:match("^[0-9]") then
          -- python identifiers can't start with a number
          val_name = "_" .. val_name
        end
        table.insert(inget(enums, enum_name, {}), {val_name, v})
      end
    end
  end
  for ename, vals in pairs(enums) do
    print(ename, #vals)
    table.sort(vals, function(a, b) return a[2] < b[2] end)
  end
  return enums
end

local function main()
  local header = terralib.includec("codegen/webgpu.h")
  local enums = gather_enums(header)

  local enum_list = {}
  for name, vals in pairs(enums) do
    table.insert(enum_list, emit_enum(name, vals))
  end
  table.sort(enum_list)
  print(table.concat(enum_list, "\n\n"))
end

return {main = main}
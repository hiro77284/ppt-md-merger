-- dump-sections.lua
-- report前提:
--   level 1 + id "chap:*"                 -> 章
--   level 2 + id "sec:*" or "ans:*"      -> 節
--   level 3 + id "subsec:*"              -> 項
--
-- 除外:
--   .unnumbered
--   #toc / #table-of-contents
--   タイトルが「目次」/ "Table of Contents"
--
-- 出力:
--   stderr に JSON と TSV を連続出力

local counters = {0, 0, 0}
local results = {}

local function has_class(attr, class_name)
  for _, c in ipairs(attr.classes or {}) do
    if c == class_name then
      return true
    end
  end
  return false
end

local function reset_lower(level)
  for i = level + 1, 3 do
    counters[i] = 0
  end
end

local function make_number(level)
  if level == 1 then
    return tostring(counters[1])
  elseif level == 2 then
    return tostring(counters[1]) .. "." .. tostring(counters[2])
  elseif level == 3 then
    return tostring(counters[1]) .. "." .. tostring(counters[2]) .. "." .. tostring(counters[3])
  end
  return ""
end

local function tsv_escape(s)
  s = tostring(s or "")
  s = s:gsub("\t", " ")
  s = s:gsub("\r", " ")
  s = s:gsub("\n", " ")
  return s
end

local function normalize_space(s)
  s = tostring(s or "")
  s = s:gsub("%s+", " ")
  s = s:gsub("^%s+", "")
  s = s:gsub("%s+$", "")
  return s
end

local function is_toc_header(h, title)
  local id = h.identifier or ""
  local norm_title = normalize_space(title)

  if id == "toc" or id == "table-of-contents" then
    return true
  end

  if norm_title == "目次" or norm_title == "Table of Contents" then
    return true
  end

  return false
end

local function classify_header(h, title)
  local level = h.level
  local id = h.identifier or ""

  if level < 1 or level > 3 then
    return nil
  end

  if has_class(h.attr, "unnumbered") then
    return nil
  end

  if is_toc_header(h, title) then
    return nil
  end

  if level == 1 and id:match("^chap:") then
    return "chapter"
  end

  if level == 2 then
    if id:match("^sec:") then
      return "section"
    end
    if id:match("^ans:") then
      return "answer"
    end
  end

  if level == 3 and id:match("^subsec:") then
    return "subsection"
  end

  return nil
end

function Header(h)
  local level = h.level
  local id = h.identifier or ""
  local title = pandoc.utils.stringify(h.content)

  local kind = classify_header(h, title)
  if not kind then
    return nil
  end

  counters[level] = counters[level] + 1
  reset_lower(level)

  local number = make_number(level)

  table.insert(results, {
    id = id,
    level = level,
    type = kind,
    number = number,
    title = title
  })

  return nil
end

function Pandoc(doc)
  io.stderr:write("===JSON===\n")
  io.stderr:write("[\n")
  for i, r in ipairs(results) do
    io.stderr:write("  " .. pandoc.json.encode(r))
    if i < #results then
      io.stderr:write(",")
    end
    io.stderr:write("\n")
  end
  io.stderr:write("]\n")

  io.stderr:write("===TSV===\n")
  io.stderr:write("id\tlevel\ttype\tnumber\ttitle\n")
  for _, r in ipairs(results) do
    io.stderr:write(
      tsv_escape(r.id) .. "\t" ..
      tsv_escape(r.level) .. "\t" ..
      tsv_escape(r.type) .. "\t" ..
      tsv_escape(r.number) .. "\t" ..
      tsv_escape(r.title) .. "\n"
    )
  end

  return doc
end

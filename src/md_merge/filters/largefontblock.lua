-- largefontblock.lua
function Div(el)
  if el.classes:includes("largefontblock") then
    if FORMAT == "typst" then
      -- #semlargefontblock（templates/semantic_macros.typ）= \Large 相当
      local out = { pandoc.RawBlock("typst", "#semlargefontblock[") }
      for _, b in ipairs(el.content) do out[#out + 1] = b end
      out[#out + 1] = pandoc.RawBlock("typst", "]")
      return out
    end
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\begin{largefontblock}"))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{largefontblock}"))
    return el
  end
end

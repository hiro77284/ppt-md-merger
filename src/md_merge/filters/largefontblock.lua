-- largefontblock.lua
function Div(el)
  if el.classes:includes("largefontblock") then
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\begin{largefontblock}"))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{largefontblock}"))
    return el
  end
end

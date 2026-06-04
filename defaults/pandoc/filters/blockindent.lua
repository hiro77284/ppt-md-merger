-- blockindent.lua
function Div(el)
  if el.classes:includes("blockindent") then
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\begin{blockindent}"))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{blockindent}"))
    return el
  end
end

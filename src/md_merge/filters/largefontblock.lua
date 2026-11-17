-- largefontblock.lua
-- Div .largefontblock を大きめの文字のブロックに lower する（Typst のみ。他の形式は素通り）。
function Div(el)
  if el.classes:includes("largefontblock") then
    if FORMAT == "typst" then
      -- #semlargefontblock（templates/semantic_macros.typ）= \Large 相当
      local out = { pandoc.RawBlock("typst", "#semlargefontblock[") }
      for _, b in ipairs(el.content) do out[#out + 1] = b end
      out[#out + 1] = pandoc.RawBlock("typst", "]")
      return out
    end
  end
end

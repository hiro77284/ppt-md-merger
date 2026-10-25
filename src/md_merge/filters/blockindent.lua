-- blockindent.lua
-- Div .blockindent を字下げブロックに lower する。
-- 字下げ量は属性 indent で指定可（例 ::: {.blockindent indent=3em}）。数値＋単位のみ許可
-- （3em / 10mm / 1.5em 等）。省略・不正値のときは既定（LaTeX 環境の 2em / CSS の 2em）。
--   LaTeX: \begin{blockindent}[<indent>] ... \end{blockindent}
--   HTML : <div class="blockindent" style="margin-left:<indent>">
--   その他の形式: 素通り
function Div(el)
  if not el.classes:includes("blockindent") then
    return nil
  end

  local indent = el.attributes["indent"]
  el.attributes["indent"] = nil  -- 消費後に除去（HTML に冗長な data-indent を残さない）
  if indent and not indent:match("^%d*%.?%d+%a+$") then
    indent = nil  -- 数値＋単位でない値は無視（CSS/LaTeX への注入防止）
  end

  if FORMAT:match("latex") then
    local opt = indent and ("[" .. indent .. "]") or ""
    table.insert(el.content, 1, pandoc.RawBlock("latex", "\\begin{blockindent}" .. opt))
    table.insert(el.content, pandoc.RawBlock("latex", "\\end{blockindent}"))
    return el
  elseif FORMAT == "typst" then
    -- #semblockindent（templates/semantic_macros.typ）。indent は数値＋単位なので Typst でも使える
    local open = indent and ("#semblockindent(indent: " .. indent .. ")[") or "#semblockindent["
    local out = { pandoc.RawBlock("typst", open) }
    for _, b in ipairs(el.content) do out[#out + 1] = b end
    out[#out + 1] = pandoc.RawBlock("typst", "]")
    return out
  elseif FORMAT:match("html") then
    if indent then
      el.attributes["style"] = "margin-left:" .. indent
    end
    return el  -- <div class="blockindent"> は素の class を保持（CSS 既定が効く）
  end

  return nil
end

-- filters/keep-together.lua
-- Div に class "keep-together" が付いていたら、直前に \Needspace{...} を挿入する
-- ついでに class は消して、他の出力形式に影響しづらくする（任意）

local DEFAULT_LINES = 10  -- デフォルトで 10 行分

local function has_class(el, name)
  if not el.classes then return false end
  for _, c in ipairs(el.classes) do
    if c == name then return true end
  end
  return false
end

local function remove_class(el, name)
  if not el.classes then return end
  local out = {}
  for _, c in ipairs(el.classes) do
    if c ~= name then table.insert(out, c) end
  end
  el.classes = out
end

function Div(el)
  if not has_class(el, "keep-together") then
    return nil
  end

  -- keep-together の属性から行数を指定できるようにする: ::: {.keep-together lines=14}
  local lines = tonumber(el.attributes["lines"]) or DEFAULT_LINES

  -- 出力が LaTeX のときだけ注入（他形式ではそのまま）
  if FORMAT:match("latex") then
    remove_class(el, "keep-together")
    local raw = pandoc.RawBlock("latex", string.format("\\Needspace{%d\\baselineskip}", lines))
    return { raw, el }
  else
    -- HTMLなどでは単に class を消す／残すは好み。残すなら remove_class を外す。
    remove_class(el, "keep-together")
    return el
  end
end

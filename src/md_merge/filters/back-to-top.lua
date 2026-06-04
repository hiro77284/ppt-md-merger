-- back-to-top.lua

function Pandoc(doc)
  if FORMAT ~= "html" and FORMAT ~= "html5" then
    return doc
  end

  local blocks = {}

  -- ページ先頭アンカー
  table.insert(blocks, pandoc.RawBlock("html", '<span id="top"></span>'))

  for _, block in ipairs(doc.blocks) do
    table.insert(blocks, block)

    -- h2以下に戻るリンクを付ける例
    if block.t == "Header" and block.level == 2 then
      table.insert(blocks, pandoc.RawBlock(
        "html",
        '<p class="back-to-top"><a href="#top">↑ top</a></p>'
      ))
    end
  end

  doc.blocks = blocks
  return doc
end

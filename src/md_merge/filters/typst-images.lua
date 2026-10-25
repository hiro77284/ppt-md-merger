-- filters/typst-images.lua
-- engine: typst 用。画像参照を resource-path から探して、.typ からの相対パスに書き換える。
--
-- LaTeX は \graphicspath で複数ディレクトリを探せるが、Typst にはその仕組みがなく、
-- 画像パスは .typ ファイルからの相対で解決される（--root の外は読めない）。そこで
-- pandoc の --resource-path（PANDOC_STATE.resource_path）を順に探し、見つかったファイルを
-- 作業ディレクトリ（= .typ を書き出すディレクトリ）からの相対パスにする。
-- --root はこれらを含む共通の上位ディレクトリを pandoc サブコマンドが指定する。
--
-- URL・data URI・絶対パス・作業ディレクトリから直接見つかるパスは書き換えない。
-- 他の出力形式では何もしない。

if FORMAT ~= "typst" then
  return {}
end

local function exists(path)
  local f = io.open(path, "rb")
  if f then
    f:close()
    return true
  end
  return false
end

local function is_external(src)
  return src:match("^%a[%w+.-]*://") or src:match("^data:") or pandoc.path.is_absolute(src)
end

local cwd = pandoc.system.get_working_directory()

function Image(el)
  local src = el.src
  if src == "" or is_external(src) or exists(src) then
    return nil
  end
  for _, dir in ipairs(PANDOC_STATE.resource_path or {}) do
    local candidate = pandoc.path.normalize(pandoc.path.join({ dir, src }))
    if not pandoc.path.is_absolute(candidate) then
      candidate = pandoc.path.join({ cwd, candidate })
    end
    if exists(candidate) then
      -- 第 3 引数 true = ".." を含む相対パスを許す（既定では作らずに元のパスを返す）
      el.src = pandoc.path.make_relative(candidate, cwd, true):gsub("\\", "/")
      return el
    end
  end
  return nil  -- 見つからない画像はそのまま（typst compile がエラーで知らせる）
end

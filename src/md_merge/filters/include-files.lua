--- include-files.lua – filter to include Markdown files
---
--- Copyright: © 2019–2021 Albert Krewinkel
--- License:   MIT – see LICENSE file for details

-- 最初の include は「入力 Markdown ファイルのあるディレクトリ」基準、
-- 再帰 include は「その include 元ファイルのあるディレクトリ」基準

-- include-base を metadata または -M include-base=... で受け取れる
-- それを 初期基準ディレクトリ として使う
-- 再帰 include のたびに 現在の基準ディレクトリをスタックで管理 する


PANDOC_VERSION:must_be_at_least '2.12'

local pandoc = require 'pandoc'
local List = require 'pandoc.List'
local path = require 'pandoc.path'
local system = require 'pandoc.system'
local utils = require 'pandoc.utils'

-- include-auto: true なら見出しレベルを自動シフト
local include_auto = false

-- 最上位入力Markdownの基準ディレクトリ
-- metadata の include-base または -M include-base=... で与える
local include_base = "."

-- 現在の include 解決基準ディレクトリを管理するスタック
local include_dir_stack = List:new()

-- 最後に見た見出しレベル
local last_heading_level = 0

-- 空文字や空白のみの行を判定
local function is_blank(s)
  return s:match("^%s*$") ~= nil
end

-- コメント行 (先頭空白を許して // ... をコメント扱い)
local function is_comment_line(s)
  return s:match("^%s*//") ~= nil
end

-- 現在の基準ディレクトリを取得
local function current_include_dir()
  if #include_dir_stack > 0 then
    return include_dir_stack[#include_dir_stack]
  end
  return include_base
end

-- include対象ファイルの実パスを解決
local function resolve_include_file(line)
  if path.is_relative(line) then
    return path.normalize(path.join({ current_include_dir(), line }))
  end
  return line
end

-- metadata を読む
local function get_vars(meta)
  if meta['include-auto'] then
    include_auto = true
  end
  if meta['include-base'] then
    include_base = utils.stringify(meta['include-base'])
    if include_base == "" then
      include_base = "."
    end
  end
end

-- 最後に見た見出しレベルを更新
local function update_last_level(header)
  last_heading_level = header.level
end

-- 取り込んだ内容の中にある相対パスを、include元ファイル基準へ補正
local function update_contents(blocks, shift_by, include_path)
  local update_contents_filter = {
    Header = function(header)
      if shift_by then
        header.level = header.level + shift_by
      end
      return header
    end,

    Link = function(link)
      if path.is_relative(link.target)
         and string.sub(path.filename(link.target), 1, 1) ~= '#'
         and not string.find(link.target, "^https?://")
      then
        link.target = path.normalize(path.join({ include_path, link.target }))
      end
      return link
    end,

    Image = function(image)
      if path.is_relative(image.src) then
        image.src = path.normalize(path.join({ include_path, image.src }))
      end
      return image
    end,

    -- include-code-files.lua 形式の include 属性にも対応
    CodeBlock = function(cb)
      if cb.attributes.include and path.is_relative(cb.attributes.include) then
        cb.attributes.include =
          path.normalize(path.join({ include_path, cb.attributes.include }))
      end
      return cb
    end
  }

  return pandoc.walk_block(
    pandoc.Div(blocks),
    update_contents_filter
  ).content
end

-- 本体
local transclude
function transclude(cb)
  if not cb.classes:includes 'include' then
    return
  end

  local format = cb.attributes['format']

  local shift_heading_level_by = 0
  local shift_input = cb.attributes['shift-heading-level-by']
  if shift_input then
    shift_heading_level_by = tonumber(shift_input)
  elseif include_auto then
    shift_heading_level_by = last_heading_level
  end

  -- 再帰前の見出しレベルを退避
  local buffer_last_heading_level = last_heading_level

  local blocks = List:new()

  for raw_line in cb.text:gmatch('[^\n\r]+') do
    local line = raw_line:gsub("^%s+", ""):gsub("%s+$", "")

    if not is_blank(line) and not is_comment_line(line) then
      local resolved_line = resolve_include_file(line)
      local fh = io.open(resolved_line)

      if not fh then
        io.stderr:write("Cannot open file " .. resolved_line .. " | Skipping includes\n")
      else
        local contents = pandoc.read(
          fh:read('*a'),
          format,
          PANDOC_READER_OPTIONS
        ).blocks
        fh:close()

        local includedir = path.directory(resolved_line)

        -- このファイルを処理している間だけ、再帰 include の基準を差し替える
        include_dir_stack:insert(includedir)

        last_heading_level = 0

        contents = system.with_working_directory(
          includedir,
          function()
            return pandoc.walk_block(
              pandoc.Div(contents),
              { Header = update_last_level, CodeBlock = transclude }
            )
          end
        ).content

        include_dir_stack:remove(#include_dir_stack)

        -- 呼び出し元の見出しレベルを復元
        last_heading_level = buffer_last_heading_level

        -- 取り込んだ内容中の相対リンク/画像パスを include 元基準で補正
        blocks:extend(
          update_contents(contents, shift_heading_level_by, includedir)
        )
      end
    end
  end

  return blocks
end

return {
  { Meta = get_vars },
  { Header = update_last_level, CodeBlock = transclude }
}

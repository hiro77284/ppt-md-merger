-- % ::: {.leadline left=6mm}
-- % ここは独立行で強く伝えたいポイントです。
-- % :::

-- % ::: {.note}
-- % ここは補足説明です。本文より少し目立たせるが、警告ほど強くはしない。
-- % :::

-- % ::: {.warning}
-- % ここは注意書きです。読み飛ばされると困る内容を置く。
-- % :::

-- % leadlinebox
-- % 枠なし、やや大きめ、ゴシック太字。擬似見出し用。

-- % notebox
-- % 薄い囲み。補足情報向け。

-- % warningbox
-- % 少し強い囲み。注意喚起向け。
-- % =======================

function Div(el)
    local allowed = {
        left = true,
        right = true,
        top = true,
        bottom = true,
        colback = true,
        colframe = true,
        boxrule = true,
        fontsize = true,
        before_skip = true,
        after_skip = true,
        frame = true,
        stretch = true,
        width = true,
        center = true
        -- style は危険なので外す
    }

    local function trim(s)
        return (s:gsub("^%s+", ""):gsub("%s+$", ""))
    end

    local function oneline(s)
        s = s:gsub("[\r\n]+", " ")
        s = s:gsub("%s%s+", " ")
        return trim(s)
    end

    local function latex_value(s)
        -- 最低限の整形だけする
        return oneline(s)
    end

    local function bool_value(s)
        s = trim(s:lower())
        if s == "true" or s == "yes" or s == "1" then
            return true
        elseif s == "false" or s == "no" or s == "0" then
            return false
        end
        return nil
    end

    local function font_key_for(kind)
        if kind == "leadline" then
            return "leadline/font"
        elseif kind == "note" then
            return "note/font"
        elseif kind == "warning" then
            return "warning/font"
        elseif kind == "widequote" then
            return "widequote/font"
        end
        return nil
    end

    local function build_options(attrs, kind)
        local opts = {}     -- オプションリストを初期化
        local base_style = kind .. "/noframe"  -- 文字列を連結してデフォルトのスタイルを設定

        -- 順序固定で処理
        local ordered_keys = {
            "frame",
            "fontsize",
            "stretch",
            "before_skip",
            "after_skip",
            "left",
            "right",
            "top",
            "bottom",
            "colback",
            "colframe",
            "boxrule",
            "width",
            "center"
        }

        for _, k in ipairs(ordered_keys) do
            local v = attrs[k]
            if v and allowed[k] then
                v = latex_value(v)

                if k == "fontsize" then
                    local fontkey = font_key_for(kind)
                    if fontkey and v ~= "" then
                        table.insert(opts, fontkey .. "={" .. v .. "}")
                    end

                elseif k == "stretch" then
                    if v ~= "" then
                        table.insert(opts, kind .. "/stretch={" .. v .. "}")
                    end

                elseif k == "before_skip" then
                    if v ~= "" then
                        table.insert(opts, "before skip={" .. v .. "}")
                    end

                elseif k == "after_skip" then
                    if v ~= "" then
                        table.insert(opts, "after skip={" .. v .. "}")
                    end

                elseif k == "frame" then
                    local b = bool_value(v)
                    if b == true then
                        base_style = kind .. "/frame"
                    elseif b == false then
                        base_style = kind .. "/noframe"
                    end

                elseif k == "center" then
                    local b = bool_value(v)
                    if b == true then
                        table.insert(opts, "center")
                    end

                else
                    if v ~= "" then
                        table.insert(opts, k .. "={" .. v .. "}")
                    end
                end
            end
        end

        table.insert(opts, 1, base_style)
        return table.concat(opts, ",")      -- カンマ区切りのオプション文字列を返す
    end

    local function wrap_env(envname, div, kind)
        local blocks = {}
        local optstr = build_options(div.attributes, kind)

        if optstr ~= "" then
            table.insert(blocks, pandoc.RawBlock(
                "latex",
                "\\begin{" .. envname .. "}[" .. optstr .. "]"
            ))
        else
            table.insert(blocks, pandoc.RawBlock(
                "latex",
                "\\begin{" .. envname .. "}"
            ))
        end

        for _, b in ipairs(div.content) do
            table.insert(blocks, b)
        end

        table.insert(blocks, pandoc.RawBlock(
            "latex",
            "\\end{" .. envname .. "}"
        ))

        return blocks
    end

    if el.classes:includes("leadline") then
        return wrap_env("leadlinebox", el, "leadline")
    elseif el.classes:includes("note") then
        return wrap_env("notebox", el, "note")
    elseif el.classes:includes("warning") then
        return wrap_env("warningbox", el, "warning")
    elseif el.classes:includes("widequote") then
        return wrap_env("widequotebox", el, "widequote")
    end
end

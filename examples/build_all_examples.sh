#!/usr/bin/env bash
# =============================================================================
# build_all_examples.sh
#   examples/ 配下のレシピ yaml を pptmdmerge で一括ビルドする。
#
# 使い方 (examples ルートで実行):
#   ./build_all_examples.sh -r [options] [PATTERN]   (実行)
#   ./build_all_examples.sh -n [options] [PATTERN]   (dry-run)
#
#   -r / -n のどちらも指定しないときは、このヘルプを表示して何も実行しない。
#
#   PATTERN を指定すると、レシピ yaml のファイル名に PATTERN を含む
#   (部分一致・大文字小文字区別) ものだけを実行する。省略時は全件。
#   例: ./build_all_examples.sh -r _pdf_recipe   /   ./build_all_examples.sh -r -k stylebase
#
# オプション:
#   -r, --run            ビルドを実行する
#   -k, --keep-going     pptmdmerge がエラーになっても続行する
#                        (既定: 最初のエラーで中断)
#   -l, --log            実行ログを保存する (既定ファイル名:
#                        build_all_examples_YYYYMMDD_HHMMSS.log, examples ルート)
#       --log-file FILE  実行ログを FILE に保存する (-l を兼ねる)
#   -n, --dry-run        実行するコマンドを表示するだけで実行しない
#                        (-r と同時指定はエラー)
#   -h, --help           このヘルプを表示する
#
# ログ保存時も標準出力に同じ内容を表示する (tee)。
# 終了コード: 全件成功 0 / 失敗あり 1 / 引数・リスト不正 2
# =============================================================================

# -----------------------------------------------------------------------------
# ビルド対象リスト
#   1 行 1 レシピ、"|" 区切りで 3 項目:
#     <examples ルートからの相対パス> | <サブコマンド> | <パラメータ>
#   - サブコマンドを空にすると DEFAULT_SUBCOMMAND (ppt_to_puremd) を使う
#   - パラメータは空白区切りの文字列 (例: --force --deletecsp off)。既定は空
#   - 空行と # で始まる行は無視する
#   ※ 値に "|" は使えない。パラメータ内で空白を含む値の引用は非対応。
# -----------------------------------------------------------------------------
DEFAULT_SUBCOMMAND="ppt_to_puremd"

RECIPES=$(cat <<'EOF'
# path                                                                  | subcommand    | parameters
pm1_simple_ppt_merge/src/simple_ppt_merge_guide_recipe.yaml             | pptmerge | --force
pm1_simple_ppt_merge/src/simple_ppt_merge_guide_pdf_recipe.yaml         | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm2_simple_numbering/src/simple_numbering_guide_recipe.yaml             | pptmerge | --force
pm2_simple_numbering/src/simple_numbering_guide_pdf_recipe.yaml         | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm3_chapter_marker_numbering/src/chapter_marker_numbering_guide_recipe.yaml | pptmerge | --force
pm3_chapter_marker_numbering/src/chapter_marker_numbering_guide_pdf_recipe.yaml | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm4_variable_replacement/src/variable_replacement_guide_recipe.yaml     | pptmerge | --force
pm4_variable_replacement/src/variable_replacement_guide_pdf_recipe.yaml | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm5_chapter_cover_insertion/src/chapter_cover_insertion_guide_recipe.yaml | pptmerge | --force
pm5_chapter_cover_insertion/src/chapter_cover_insertion_guide_pdf_recipe.yaml | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm6_stylebase/src/stylebase_guide_recipe.yaml                           | pptmerge | --force
pm6_stylebase/src/stylebase_guide_pdf_recipe.yaml                       | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm7_splitted_insertion/src/splitted_insertion_guide_recipe.yaml         | pptmerge | --force
pm7_splitted_insertion/src/splitted_insertion_guide_pdf_recipe.yaml     | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm8_delete_csp/src/delete_csp_guide_recipe.yaml                         | pptmerge | --force
pm8_delete_csp/src/delete_csp_guide_pdf_recipe.yaml                     | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm9_delete_csl/src/delete_csl_guide_recipe.yaml                         | pptmerge | --force
pm9_delete_csl/src/delete_csl_guide_pdf_recipe.yaml                     | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm10_memo_temp/src/memo_temp_guide_recipe.yaml                          | pptmerge | --force
pm10_memo_temp/src/memo_temp_guide_pdf_recipe.yaml                      | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pm11_title_filename/src/title_filename_guide_recipe.yaml                | pptmerge | --force
pm11_title_filename/src/title_filename_guide_pdf_recipe.yaml            | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
pdf1_minimum/src/pdf1_minimum_pdf_recipe.yaml                           | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
#pdf2_minimum/src/pdf1_minimum_pdf_recipe.yaml                          | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
overview/src/overview_pdf_recipe.yaml                                   | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
# semantic_notation_guide/semantic_notation_recipe.yaml                 | ppt_build | --githubmd --transfer --pdf --yes-clear-dir     # これは別種の方法でビルドするので除外
readme_file/src/readme_file_pdf_recipe.yaml                             | ppt_build | --githubmd --transfer --pdf --yes-clear-dir
EOF
)

# -----------------------------------------------------------------------------
# 以下は実装部 (通常は編集不要)
# -----------------------------------------------------------------------------
EXAMPLES_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

KEEP_GOING=0
SAVE_LOG=0
LOG_FILE=""
DRY_RUN=0
RUN=0
PATTERN=""

usage() {
    sed -n '2,/^# =====/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        -k|--keep-going) KEEP_GOING=1 ;;
        -l|--log)        SAVE_LOG=1 ;;
        --log-file)
            [ $# -ge 2 ] || { echo "error: --log-file には FILE が必要です" >&2; exit 2; }
            SAVE_LOG=1; LOG_FILE="$2"; shift ;;
        --log-file=*)    SAVE_LOG=1; LOG_FILE="${1#*=}" ;;
        -r|--run)        RUN=1 ;;
        -n|--dry-run)    DRY_RUN=1 ;;
        -h|--help)       usage; exit 0 ;;
        -*) echo "error: 不明なオプション: $1" >&2; usage >&2; exit 2 ;;
        *)
            [ -z "$PATTERN" ] || { echo "error: PATTERN は 1 つだけ指定できます" >&2; exit 2; }
            PATTERN="$1" ;;
    esac
    shift
done

if [ $RUN -eq 1 ] && [ $DRY_RUN -eq 1 ]; then
    echo "error: -r/--run と -n/--dry-run は同時に指定できません" >&2; exit 2
fi
if [ $RUN -eq 0 ] && [ $DRY_RUN -eq 0 ]; then
    usage; exit 0
fi

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

run_all() {
    local total=0 ok=0 ng=0
    local -a failed=()
    local line path sub params dir file rc
    local -a args

    cd "$EXAMPLES_ROOT" || return 2
    echo "=== build_all_examples.sh  $(date '+%Y-%m-%d %H:%M:%S') ==="
    echo "examples root: $EXAMPLES_ROOT"
    echo "on error: $([ $KEEP_GOING -eq 1 ] && echo continue || echo stop)"
    [ $DRY_RUN -eq 1 ] && echo "dry-run: yes"
    [ -n "$PATTERN" ] && echo "pattern: $PATTERN"
    echo

    # リストは fd 3 から読む (stdin は pptmdmerge の確認入力用に端末のまま残す)
    while IFS= read -r -u 3 line || [ -n "$line" ]; do
        line=$(trim "$line")
        case "$line" in ''|'#'*) continue ;; esac

        IFS='|' read -r path sub params <<<"$line"
        path=$(trim "$path"); sub=$(trim "$sub"); params=$(trim "$params")
        [ -n "$sub" ] || sub="$DEFAULT_SUBCOMMAND"
        dir=$(dirname "$path"); file=$(basename "$path")
        if [ -n "$PATTERN" ] && [[ "$file" != *"$PATTERN"* ]]; then
            continue
        fi

        total=$((total + 1))
        read -r -a args <<<"$params"

        echo "----- [$total] $path"
        if [ ! -f "$EXAMPLES_ROOT/$path" ]; then
            echo "ERROR: レシピが見つかりません: $path"
            rc=2
        elif ! cd "$EXAMPLES_ROOT/$dir"; then
            echo "ERROR: cd できません: $dir"
            rc=2
        else
            echo "\$ (cd $dir) pptmdmerge $sub $file${params:+ $params}"
            if [ $DRY_RUN -eq 1 ]; then
                rc=0
            else
                pptmdmerge "$sub" "$file" "${args[@]}" 2>&1
                rc=$?
            fi
            cd "$EXAMPLES_ROOT" || return 2
        fi

        if [ $rc -eq 0 ]; then
            ok=$((ok + 1))
            echo "OK"
        else
            ng=$((ng + 1))
            failed+=("$path (exit $rc)")
            echo "FAILED (exit $rc)"
            if [ $KEEP_GOING -eq 0 ]; then
                echo
                echo "エラーのため中断しました (続行するには -k / --keep-going)"
                break
            fi
        fi
        echo
    done 3<<<"$RECIPES"

    cd "$EXAMPLES_ROOT" || return 2
    if [ $total -eq 0 ]; then
        echo "ERROR: 対象のレシピがありません${PATTERN:+ (pattern: $PATTERN)}"
        return 2
    fi
    echo "=== summary: total(run)=$total ok=$ok failed=$ng ==="
    local f
    for f in "${failed[@]}"; do echo "  FAILED: $f"; done

    [ $ng -eq 0 ]
}

if [ $SAVE_LOG -eq 1 ]; then
    [ -n "$LOG_FILE" ] || LOG_FILE="$EXAMPLES_ROOT/build_all_examples_$(date '+%Y%m%d_%H%M%S').log"
    echo "log file: $LOG_FILE"
    run_all 2>&1 | tee "$LOG_FILE"
    status=${PIPESTATUS[0]}
else
    run_all
    status=$?
fi

cd "$EXAMPLES_ROOT"
exit "$status"

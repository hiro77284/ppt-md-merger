#!/usr/bin/env bash
set -e

# このスクリプトは、すべてのexamplesをビルドするためのスクリプトです。

TEXTCONV_CONFIG=/d/DOCS/SWPJs/textconv/textconv_togithub.yaml
TEXTCONV_OVERWRITE=--overwrite
PPTMERGE_FORCE=--force

KEEP_WORK=--keep-work

DO_OVERVIEW=true

DEBUG=--debug

# 概要説明書のビルド
if [[ "$DO_OVERVIEW" == true ]]; then
    echo "===========building overview example... ==========="
    cd overview
    pptmdmerge.exe ppt_to_pdf overview_recipe.yaml $KEEP_WORK
    textconv build/overview_merged_rendered.md -o ../../README.md --config $TEXTCONV_CONFIG $TEXTCONV_OVERWRITE --from-base examples/overview/build/ --to-base .
    pptmdmerge.exe pptmerge overview_recipe.yaml
    cd ..
fi




targets=(
    # pm1
    # pm2
    # pm3
    # pm4
    # pm5
    # pm6
    # pm7
    # pm8
    # pm9
    # pm10
    # pm11
)

declare -A samplenames

samplenames[pm1]="simple_ppt_merge"
samplenames[pm2]="simple_numbering"
samplenames[pm3]="chapter_marker_numbering"
samplenames[pm4]="variable_replacement"
samplenames[pm5]="chapter_cover_insertion"
samplenames[pm6]="stylebase"
samplenames[pm7]="splitted_insertion"
samplenames[pm8]="delete_csp"
samplenames[pm9]="delete_csl"
samplenames[pm10]="memo_temp"
samplenames[pm11]="title_filename"


for target in "${targets[@]}"
do
    echo "checking $target"
    echo cd ${target}_${samplenames[$target]}
    cd ${target}_${samplenames[$target]}
    echo "===========building ${samplenames[$target]} PDF ==========="
    echo pptmdmerge.exe ppt_to_pdf ${samplenames[$target]}_pdf_recipe.yaml $PPTMERGE_FORCE $KEEP_WORK
    pptmdmerge.exe ppt_to_pdf ${samplenames[$target]}_pdf_recipe.yaml $PPTMERGE_FORCE
    echo "===========building ${samplenames[$target]} README ==========="
    echo textconv build/${samplenames[$target]}_rendered.md -o README.md --config $TEXTCONV_CONFIG $TEXTCONV_OVERWRITE --from-base build --to-base .
    textconv build/${samplenames[$target]}_rendered.md -o README.md --config $TEXTCONV_CONFIG $TEXTCONV_OVERWRITE --from-base build --to-base . $DEBUG
    echo "===========building ${samplenames[$target]} PPTX ==========="
    echo pptmdmerge.exe pptmerge ${samplenames[$target]}_recipe.yaml $PPTMERGE_FORCE
    pptmdmerge.exe pptmerge ${samplenames[$target]}_recipe.yaml $PPTMERGE_FORCE
    echo cd ..
    cd ..
    read -p "Enterキーを押すと続行します..." < /dev/tty
done



# pm1 のビルド
# if [[ "$DO_PM1" == true ]]; then
#     echo "===========building pm1_simple_ppt_merge example... ==========="
#     cd pm1_simple_ppt_merge
#     echo "===========building pm1_simple_ppt PDF ==========="
#     pptmdmerge.exe ppt_to_pdf simple_ppt_merge_pdf_recipe.yaml $PPTMERGE_FORCE
#     echo "===========building pm1_simple_ppt README ==========="
#     echo textconv build/simple_ppt_rendered.md -o README.md --config $TEXTCONV_CONFIG $TEXTCONV_OVERWRITE --from-base . --to-base .
#     textconv build/simple_ppt_rendered.md -o README.md --config $TEXTCONV_CONFIG $TEXTCONV_OVERWRITE --from-base . --to-base . $DEBUG
#     echo "===========building pm1_simple_ppt PPTX ==========="
#     pptmdmerge.exe pptmerge simple_ppt_merge_recipe.yaml $PPTMERGE_FORCE
#     cd ..
# fi

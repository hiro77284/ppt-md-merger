{{#id:subsection:ppt_md_merger_overview:slide16_2}} 
### 2. Create merge recipe YAML

PowerPointファイルを単純結合する結合指示書のサンプル

```
output: 
  pptxfilename: merged.pptx        # 結合後のpptxファイルのファイル名

procedure:
  - operation: insertpptx		 # 結合後対象のファイルを列挙する
    pptxfilename: 00_intro.pptx
  - operation: insertpptx
    pptxfilename: 10_basic.pptx
  - operation: insertpptx
    pptxfilename: 20_example.pptx
```
<!-- source: ../mds/memo_temp_guide_slide1_md.md -->
<!-- md_merge_rawtitle: 作業用のメモを書く -->
<!-- #id:section:memo_temp_guide:slide1 -->
## 作業用のメモを書く

長い研修テキストの制作中には、 「とりあえずたたき台を書いておくけど、必ず直前に最終確認しろ！」 というような事項がどうしても出てくるものです。 紙の資料なら付箋紙を貼るところですがデジタル文書ではそれができない。 そこでパワポ資料では付箋紙代わりに目立つ図形にそうした注意書きを書いて残しておいたりしますが、これは本番資料からは必ず削除しなければならないもの。

ところが・・・そう、残ってしまうことがあるんですね。

そこで、MEMO/TEMPマーカーです。 #MEMO# または #TEMP# という文字列を含むシェイプは deletecsp に関係なく必ず削除されます。

MEMO、TEMP の動作は同じです。

結合指示書への記入は不要です。




<img src="readme-images/memo-temp-guide-slide1-fig.png" alt="" width="95%">

<img src="readme-images/memo-temp-guide-keyvisual.png" alt="" width="90%">





<!-- source: ../mds/memo_temp_guide_slide2_md.md -->
<!-- md_merge_rawtitle: MEMO, TEMP サンプル -->
<!-- #id:section:memo_temp_guide:slide2 -->
## MEMO, TEMP サンプル

下記の 「シェイプ」は無条件で消去されます。画像は残ります。
（PDFファイル中では両方とも残って見えますが、マージされた .pptx からは削除されます）



<img src="readme-images/memo-temp-guide-slide2-fig.png" alt="" width="95%">





<!-- source: ../mds/memo_temp_guide_slide3_md.md -->
<!-- md_merge_rawtitle: テーブルシェイプはテーブルごと消去 -->
<!-- #id:section:memo_temp_guide:slide3 -->
## テーブルシェイプはテーブルごと消去

テーブルセルに MEMO, TEMPマーカーがある場合は、テーブルごと消去されます。
（PDFファイル中では両方とも残って見えますが、マージされた .pptx からは削除されます）



<img src="readme-images/memo-temp-guide-slide3-fig.png" alt="" width="95%">


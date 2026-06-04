<!-- source: extracted/chapter_cover_insertion_guide_slide1_md.md -->
<!-- #id:section:chapter_cover_insertion_guide:slide1 -->
## Chapter Cover 挿入運用

章・節、つまり Chapter/Section 構造の書籍にはしばしば 「章とびら（Chapter Cover）」 をつけます。これは章全体の説明や、各節の概要、章単位での目次などを含むスライドであり、いわば  **「前置き」** です。

それに対して、本題は **「節」** の部分に記述します。通常、この部分を文書部品マスターとして個別の pptx ファイルとして管理します。つまり、個別の文書部品マスターpptxには「本題」 部分しか入っていないことがあります。

そこで、Chapter Cover が必要なら別途挿入します。


![](figures/chapter_cover_insertion_guide_slide1_fig.png){ width=95% }

![](figures/chapter_cover_insertion_guide_keyvisual.png){ width=80% }



機能としては単なる operation:insertpptx と varsであり、Chapter Cover 用ファイルを用意して中身を変数置換することで実現します。

<!-- source: D:/sandbox/common_assets/tex_newpage.md -->




<!-- source: extracted/chapter_cover_insertion_guide_slide2_md.md -->
<!-- #id:section:chapter_cover_insertion_guide:slide2 -->
## operation: chapter が使いにくい問題

Chapter Cover 挿入運用の詳しい説明をします。

たとえばいずれも細かい情報の入った２つのpptxを結合したい、その際、話題が違うので Chapter 番号を変えたいとします。 operation: chapter を加えることで、Chapter 番号を変えること自体は可能ですが、この方式にはちょっとした欠点があります。


![](figures/chapter_cover_insertion_guide_slide2_fig.png){ width=95% }


<!-- source: D:/sandbox/common_assets/tex_newpage.md -->




<!-- source: extracted/chapter_cover_insertion_guide_slide3_md.md -->
<!-- #id:section:chapter_cover_insertion_guide:slide3 -->
## Chapter Cover で話題の転換を明示したい

章・節番号がついてはいても、全体として細かい情報が続いているので、読者には　「急に話題が変わった」　印象を与えやすいのです。


![](figures/chapter_cover_insertion_guide_slide3_fig.png){ width=95% }


はっきりとデザインの違う Chapter Cover スライドを挿入しておけば、この問題を解決できます。

<!-- source: D:/sandbox/common_assets/tex_newpage.md -->




<!-- source: extracted/chapter_cover_insertion_guide_slide4_md.md -->
<!-- #id:section:chapter_cover_insertion_guide:slide4 -->
## Chapter Cover の挿入方法

そこで、Chapter Cover 用の1枚だけのスライドを作ってoperation: chapter の代わりに operation: insertpptx で挿入します。

ただし、同じファイルだとChapterが分からないので、テンプレートの中身を変数で書き換えられるようにします。


![](figures/chapter_cover_insertion_guide_slide4_fig.png){ width=95% }


<!-- source: D:/sandbox/common_assets/tex_newpage.md -->




<!-- source: extracted/chapter_cover_insertion_guide_slide5_md.md -->
<!-- #id:section:chapter_cover_insertion_guide:slide5 -->
## Chapter Cover テンプレートファイルの作り方

Chapter Cover テンプレートファイルの作り方です。

#CHAPT# マーカーを入れておくこと、TITLE プレースホルダーに置換用の変数を入れておくことがポイントです。


![](figures/chapter_cover_insertion_guide_slide5_fig.png){ width=95% }


概要説明文やChapter目次やも入れたければ、それも変数にしておけば置き換えられます。
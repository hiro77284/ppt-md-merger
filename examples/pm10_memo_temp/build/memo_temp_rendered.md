<!-- source: extracted/memo_temp_guide_slide1_md.md -->
<!-- #id:section:memo_temp_guide:slide1 -->
## 作業用のメモを書く

長い研修テキストの制作中には、 「とりあえずたたき台を書いておくけど、必ず直前に最終確認しろ！」 というような事項がどうしても出てくるものです。 紙の資料なら付箋紙を貼るところですがデジタル文書ではそれができない。 そこでパワポ資料では付箋紙代わりに目立つ図形にそうした注意書きを書いて残しておいたりしますが、これは本番資料からは必ず削除しなければならないもの。

ところが・・・そう、残ってしまうことがあるんですね。

そこで、MEMO/TEMPマーカーです。 #MEMO# または #TEMP# という文字列を含むシェイプは deletecsp に関係なく必ず削除されます。

MEMO、TEMP の動作は同じです。

結合指示書への記入は不要です。


```{=latex}
\par\vspace{1\baselineskip}
\begin{center}
```

![](figures/memo_temp_guide_slide1_fig.png){ width=95% }

![](figures/memo_temp_guide_keyvisual.png){ width=90% }


```{=latex}
\end{center}
\par\vspace{1\baselineskip}
```

<!-- source: D:/DOCS/SWPJs/md_merge/defaults/common_assets/tex_newpage.md -->

\newpage



<!-- source: extracted/memo_temp_guide_slide2_md.md -->
<!-- #id:section:memo_temp_guide:slide2 -->
## MEMO, TEMP サンプル

下記の 「シェイプ」は無条件で消去されます。画像は残ります。
（PDFファイル中では両方とも残って見えますが、マージされた .pptx からは削除されます）

```{=latex}
\par\vspace{1\baselineskip}
\begin{center}
```

![](figures/memo_temp_guide_slide2_fig.png){ width=95% }

```{=latex}
\end{center}
\par\vspace{1\baselineskip}
```

<!-- source: D:/DOCS/SWPJs/md_merge/defaults/common_assets/tex_2line.md -->

\par\vspace{2\baselineskip}



<!-- source: extracted/memo_temp_guide_slide3_md.md -->
<!-- #id:section:memo_temp_guide:slide3 -->
## テーブルシェイプはテーブルごと消去

テーブルセルに MEMO, TEMPマーカーがある場合は、テーブルごと消去されます。
（PDFファイル中では両方とも残って見えますが、マージされた .pptx からは削除されます）

```{=latex}
\par\vspace{1\baselineskip}
\begin{center}
```

![](figures/memo_temp_guide_slide3_fig.png){ width=95% }

```{=latex}
\end{center}
\par\vspace{1\baselineskip}
```
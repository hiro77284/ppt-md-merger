{{#id:section:simple_numbering_guide:slide5}}
## chap_section方式のアルゴリズム

chapt_section 方式は、pptmerge のプロセスが内部的に付番用変数を管理して行うものです。
chapter, section の変数はいずれも処理開始前は 0 であり、operation を経る都度、加算やリセットされます。"+" の部分を変えれば単純なカウントアップ以外の操作も可能です。

```bash
"+"  1 加算
"+2" 2 加算
"2" 2でリセットする
```

section はスライドが進むことにより自動的にカウントアップされます。
chapter 増やすにはここで説明した　operation: chapter の操作をするか、あるいは スライド上のマーカーによりカウントする方法もあります（別項目にて説明します）。


```{=latex}
\begin{center}
```

![](figures/simple_numbering_guide_slide5_fig.png){ width=95% }

```{=latex}
\end{center}
```
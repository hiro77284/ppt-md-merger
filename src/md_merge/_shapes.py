"""PPTX シェイプの名前解決（pptimgexport / pptyamlexport 共通）。

名前でシェイプを引く処理は `pptimgexport`（切り出し範囲の特定）と `pptyamlexport`
（baseframe / slot の座標算出）の両方にあり、どちらも「スライド直下のシェイプだけ
が使える」という同じ制約を持つ。その制約と診断をここに集約する。

**グループ内のシェイプは座標計算に使えない。** python-pptx はグループの子シェイプの
``left`` / ``top`` を親グループの**子座標系**（``a:chOff`` / ``a:chExt``）のまま返す
ため、スライド基準の座標にするにはグループの offset / extent による写像が必要になる。
その変換を行わずに再帰探索だけ足すと、警告は消えるが切り出し範囲がズレるという最悪の
結果になるので、ここでは**探すが使わない**。見つけた場合は「グループを解除せよ」と
分かる診断を返す。
"""

from __future__ import annotations


def iter_all_shapes(shapes):
    """シェイプをグループ内まで再帰的に列挙する（グループ自身も含む）。"""
    for shape in shapes:
        if getattr(shape, "shapes", None) is not None:
            yield shape
            yield from iter_all_shapes(shape.shapes)
        else:
            yield shape


def find_shape(slide, name: str):
    """スライド直下から名前でシェイプを引く。

    Returns:
        (shape, found_in_group): shape が None のとき found_in_group が True なら
        グループ内に同名シェイプが存在する（＝グループ解除で解決する）。
    """
    for shape in slide.shapes:
        if shape.name == name:
            return shape, False
    for shape in iter_all_shapes(slide.shapes):
        if shape.name == name:
            return None, True
    return None, False


def not_found_reason(name: str, in_group: bool) -> str:
    """シェイプを引けなかった理由を説明する文字列を返す。"""
    if in_group:
        return (
            f"シェイプ '{name}' はグループ内にあります。グループ内シェイプの座標は"
            "親の子座標系で表されるため使えません（グループを解除してください）"
        )
    return f"シェイプ '{name}' が見つかりません"

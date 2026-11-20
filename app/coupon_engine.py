"""优惠券与订单金额计算引擎。

规则见 01-需求规格.md。金额一律用「分」结算，不出现浮点数 ——
0.1 + 0.2 在浮点里不等于 0.3，金额算错一次就是一次客诉。

这个模块是研发提供给测试的「算价逻辑」，测试按需求规格验证它。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 运费规则
SHIPPING_FEE = 1200            # 12 元
FREE_SHIPPING_THRESHOLD = 9900  # 满 99 包邮

# 券类型
KIND_FULL = "full_reduction"   # 满减
KIND_DISCOUNT = "discount"     # 折扣
KIND_CATEGORY = "category"     # 品类券
KIND_NEWUSER = "newuser"       # 新人券（无门槛）


@dataclass
class Item:
    name: str
    category: str          # ceramic / other
    price_cents: int
    qty: int = 1
    is_special: bool = False   # 特价商品不参与任何优惠


@dataclass
class Coupon:
    code: str
    kind: str
    threshold_cents: int = 0     # 门槛（满减/品类券用）
    off_cents: int = 0           # 减免金额（满减/品类/新人券用）
    rate: int = 100              # 折扣率，85 表示 85 折
    cap_cents: int | None = None  # 折扣券封顶
    category: str | None = None   # 品类券限定品类


@dataclass
class Result:
    goods_total: int
    shipping: int
    discount: int
    payable: int
    applied: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def calc(items: list[Item], coupons: list[Coupon]) -> Result:
    """算一笔订单的应付金额。"""
    if not items:
        raise ValueError("订单不能为空")

    goods_total = sum(i.price_cents * i.qty for i in items)

    # 特价商品计入总额，但不参与优惠
    base = sum(i.price_cents * i.qty for i in items if not i.is_special)

    # 运费：按商品总额判断是否包邮
    shipping = 0 if goods_total >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE

    # 折扣券与其他券互斥（R4）
    discounts = [c for c in coupons if c.kind == KIND_DISCOUNT]
    others = [c for c in coupons if c.kind != KIND_DISCOUNT]
    if discounts and others:
        raise ValueError("折扣券不能与满减/品类券叠加使用")
    if len(discounts) > 1 or len([c for c in others if c.kind == KIND_FULL]) > 1:
        raise ValueError("同类券只能用一张")

    applied: list[str] = []
    rejected: list[str] = []
    total_off = 0

    # ---------- 折扣券 ----------
    if discounts:
        c = discounts[0]
        off = base * (100 - c.rate) // 100
        if c.cap_cents is not None:
            off = min(off, c.cap_cents)
        total_off += off
        applied.append(c.code)
        return _finish(goods_total, shipping, total_off, applied, rejected)

    # ---------- 品类券：只对该品类、且非特价的商品生效 ----------
    for c in [x for x in others if x.kind == KIND_CATEGORY]:
        cat_base = sum(
            i.price_cents * i.qty
            for i in items
            if i.category == c.category and not i.is_special
        )
        if goods_total >= c.threshold_cents:
            total_off += c.off_cents
            applied.append(c.code)
        else:
            rejected.append(c.code)

    # ---------- 满减 / 新人券 ----------
    for c in [x for x in others if x.kind in (KIND_FULL, KIND_NEWUSER)]:
        # 门槛按「商品总额 + 运费」判断
        reachable = (goods_total + shipping) >= c.threshold_cents
        if reachable:
            total_off += c.off_cents
            applied.append(c.code)
        else:
            rejected.append(c.code)

    return _finish(goods_total, shipping, total_off, applied, rejected)


def _finish(goods_total, shipping, total_off, applied, rejected) -> Result:
    payable = goods_total - total_off + shipping
    return Result(
        goods_total=goods_total,
        shipping=shipping,
        discount=total_off,
        payable=payable,
        applied=applied,
        rejected=rejected,
    )

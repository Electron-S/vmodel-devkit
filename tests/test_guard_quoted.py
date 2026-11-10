"""Guard false positive found by the real G6 drill session S1 (2026-11-10, release core ce81befa; also 0.1.3-0.2.0).

The agent ran `"<plugin>/bin/vmodel" new-wi --title "..." --request "... 첫 줄 'ORDER <order_id>' ..."`, the user's
request text verbatim. _is_validator_call looked for shell metacharacters (; & | ` < > $( ) in the whole command,
quoted arguments included, so the call was not recognised as a validator call; the '>' inside the quotes then counted
as a write and the command names the release path, so the guard denied it as "would modify the Validator Core".
Any request text with < or > (comparisons, placeholders, generics) made work item creation impossible.
Fix: metacharacters inside single quotes, and inside double quotes except command substitution (` and $( ), are text.
RED target: git archive fa815b3 plugins/vmodel.
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VM = f'"{PLUGIN / "bin" / "vmodel"}"'
S1_REQUEST = ("주문 가격 계산과 영수증 출력 기능을 추가해 주세요. 영수증 모듈 src/orderdesk/receipt.py: "
              "render_receipt(order, pricer=price_order) — order는 {order_id, lines}. 첫 줄 'ORDER <order_id>', "
              "품목마다 '<sku> x<qty> <금액>', 끝에 'SUBTOTAL <소계>', 'DISCOUNT <할인>', 'TOTAL <합계>'.")


class GuardQuotedTextRed(_Guard):
    def test_request_text_with_angle_brackets_is_a_validator_call(self):
        cmds = [f'{VM} new-wi --title "주문 가격 계산과 영수증 출력" --request "{S1_REQUEST}"',
                f'{VM} new-wi --title "t" --request "x > 0 and y < 3"',
                f"{VM} new-wi --title 't' --request 'single <quoted> > text'",
                f'{VM} new-wi --title "t" --request "he said \\"a > b\\" twice"']
        denied = {c[-60:]: self.decide(c) for c in cmds}
        self.assertEqual({c: r for c, r in denied.items() if r is not None}, {}, "RED-TARGET should be allowed")


class GuardQuotedTextChar(_Guard):
    def test_real_redirections_and_substitutions_stay_denied(self):
        self.assert_denied([f"{VM} status > .vmodel/state/ledger.jsonl",
                            f'{VM} new-wi --title "t" --request "a" > "{PLUGIN}/bin/x"',
                            f"{VM} new-wi --title 't' --request 'a' > {PLUGIN}/validator/x.py",
                            f'{VM} new-wi --title "t" --request "$(rm -rf .vmodel/state)"',
                            f'{VM} new-wi --title "t" --request "`rm -rf .vmodel/state`"',
                            f'{VM} new-wi --title "t" --request "a"; rm -rf .vmodel/state',
                            f'{VM} new-wi --title "t" --request "a" && touch {PLUGIN}/bin/x'])

    def test_quoted_separators_without_a_write_stay_allowed(self):
        self.assert_allowed([f'{VM} new-wi --title "t" --request "a; b | c & d"', f"{VM} status"])


if __name__ == "__main__":
    unittest.main()

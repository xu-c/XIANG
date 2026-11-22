# XiangQi Wizard Light

The unmodified `book.js`, `position.js`, `search.js`, and upstream license come from [xqbase/xqwlight](https://github.com/xqbase/xqwlight/tree/6221733f1f79b3acb44cce6f83dc6100443cb2c9), commit `6221733f1f79b3acb44cce6f83dc6100443cb2c9`. See the original copyright and license notices in the bundled scripts. `run.cjs` is XIANG's GPL-3.0-or-later command-line adapter.

The three search budgets (10, 100, 1000 milliseconds), hash parameter (16), and maximum search depth use the upstream [JavaScript board](https://github.com/xqbase/xqwlight/blob/6221733f1f79b3acb44cce6f83dc6100443cb2c9/JavaScript/index.htm). They are iteration budgets, and elapsed time may be longer for a search iteration. Opening-book moves can be immediate at every level.


#lang racket

;; Generate a 100-function program for the real codebase demo.
;; Domain: financial analytics pipeline — naturally decomposes into
;; binary operations (amount pairs, rate pairs, weighted combinations).

(define (gen)
  ;; Layer 0: 15 primitives (leaf functions, no calls)
  (define prims
    '((defn scale-rate [x y] (* x (+ y 1)))
      (defn discount [x y] (/ x (+ y 1)))
      (defn compound [x y] (* x (* y y)))
      (defn blend [x y] (+ (* x y) (- x y)))
      (defn clip [x y] (- x (* y y)))
      (defn ratio [x y] (/ (+ x y) (* x y)))
      (defn delta [x y] (- (* x x) (* y y)))
      (defn norm [x y] (/ x (+ (* y y) 1)))
      (defn weight [x y] (* x (/ y (+ x y))))
      (defn spread [x y] (- (/ x y) (/ y x)))
      (defn cap [x y] (+ x (* x y)))
      (defn floor-val [x y] (- x (* x y)))
      (defn avg [x y] (/ (+ x y) 2))
      (defn pct [x y] (* (/ x y) 100))
      (defn margin [x y] (/ (- x y) x))))

  ;; Layer 1: 20 functions using primitives
  (define layer1
    '((defn interest [x y] (scale-rate x y))
      (defn present-val [x y] (discount (compound x y) y))
      (defn future-val [x y] (compound x (scale-rate x y)))
      (defn net-return [x y] (delta (scale-rate x y) y))
      (defn risk-adj [x y] (blend (norm x y) (weight x y)))
      (defn vol-scale [x y] (clip (spread x y) y))
      (defn sharpe [x y] (ratio (net-return x y) (vol-scale x y)))
      (defn sortino [x y] (ratio (net-return x y) (floor-val x y)))
      (defn alpha [x y] (delta (net-return x y) (interest x y)))
      (defn beta [x y] (ratio (spread x y) (delta x y)))
      (defn drawdown [x y] (margin (cap x y) (floor-val x y)))
      (defn recovery [x y] (ratio (cap x y) (floor-val x y)))
      (defn turnover [x y] (avg (pct x y) (pct y x)))
      (defn liquidity [x y] (blend (avg x y) (spread x y)))
      (defn exposure [x y] (weight (cap x y) (norm x y)))
      (defn hedge-ratio [x y] (norm (beta x y) (vol-scale x y)))
      (defn cost-basis [x y] (avg (discount x y) (compound x y)))
      (defn yield-curve [x y] (blend (interest x y) (present-val x y)))
      (defn duration [x y] (weight (present-val x y) y))
      (defn convexity [x y] (delta (duration x y) (duration y x)))))

  ;; Layer 2: 25 functions composing layer 1
  (define layer2
    '((defn port-return [x y] (blend (net-return x y) (alpha x y)))
      (defn port-risk [x y] (avg (vol-scale x y) (drawdown x y)))
      (defn port-sharpe [x y] (ratio (port-return x y) (port-risk x y)))
      (defn risk-parity [x y] (weight (exposure x y) (vol-scale x y)))
      (defn opt-weight [x y] (norm (sharpe x y) (beta x y)))
      (defn rebal-cost [x y] (blend (turnover x y) (cost-basis x y)))
      (defn tax-impact [x y] (margin (net-return x y) (cost-basis x y)))
      (defn after-tax [x y] (delta (net-return x y) (tax-impact x y)))
      (defn real-return [x y] (delta (after-tax x y) (interest x y)))
      (defn info-ratio [x y] (ratio (alpha x y) (vol-scale x y)))
      (defn tracking-err [x y] (delta (port-return x y) (net-return x y)))
      (defn max-drawdown [x y] (clip (drawdown x y) (recovery x y)))
      (defn calmar [x y] (ratio (port-return x y) (max-drawdown x y)))
      (defn var-95 [x y] (blend (port-risk x y) (vol-scale x y)))
      (defn cvar [x y] (avg (var-95 x y) (max-drawdown x y)))
      (defn stress-test [x y] (delta (cvar x y) (port-return x y)))
      (defn liq-score [x y] (blend (liquidity x y) (turnover x y)))
      (defn capacity [x y] (weight (liq-score x y) (exposure x y)))
      (defn impl-short [x y] (margin (rebal-cost x y) (port-return x y)))
      (defn slip-model [x y] (blend (impl-short x y) (liq-score x y)))
      (defn net-alpha [x y] (delta (alpha x y) (rebal-cost x y)))
      (defn gross-exp [x y] (avg (exposure x y) (hedge-ratio x y)))
      (defn net-exp [x y] (delta (gross-exp x y) (hedge-ratio x y)))
      (defn lever-ratio [x y] (ratio (gross-exp x y) (net-exp x y)))
      (defn margin-req [x y] (blend (lever-ratio x y) (var-95 x y)))))

  ;; Layer 3: 25 functions composing layers 1+2
  (define layer3
    '((defn port-score [x y] (blend (port-sharpe x y) (calmar x y)))
      (defn risk-budget [x y] (weight (var-95 x y) (cvar x y)))
      (defn alloc-signal [x y] (delta (opt-weight x y) (risk-parity x y)))
      (defn trade-signal [x y] (blend (alloc-signal x y) (net-alpha x y)))
      (defn order-size [x y] (weight (trade-signal x y) (capacity x y)))
      (defn exec-quality [x y] (margin (slip-model x y) (impl-short x y)))
      (defn post-trade [x y] (delta (port-return x y) (slip-model x y)))
      (defn attrib-alpha [x y] (delta (post-trade x y) (net-return x y)))
      (defn attrib-timing [x y] (delta (attrib-alpha x y) (alpha x y)))
      (defn attrib-select [x y] (delta (alpha x y) (attrib-timing x y)))
      (defn perf-fee [x y] (blend (attrib-alpha x y) (after-tax x y)))
      (defn mgmt-fee [x y] (pct (gross-exp x y) y))
      (defn total-cost [x y] (avg (perf-fee x y) (mgmt-fee x y)))
      (defn net-perf [x y] (delta (post-trade x y) (total-cost x y)))
      (defn client-return [x y] (delta (net-perf x y) (interest x y)))
      (defn peer-rank [x y] (ratio (port-score x y) (info-ratio x y)))
      (defn mandate-fit [x y] (blend (risk-budget x y) (net-exp x y)))
      (defn compliance [x y] (margin (lever-ratio x y) (margin-req x y)))
      (defn report-card [x y] (avg (peer-rank x y) (mandate-fit x y)))
      (defn risk-alert [x y] (delta (stress-test x y) (risk-budget x y)))
      (defn rebal-trigger [x y] (blend (alloc-signal x y) (risk-alert x y)))
      (defn cash-flow [x y] (delta (client-return x y) (total-cost x y)))
      (defn nav-impact [x y] (blend (cash-flow x y) (slip-model x y)))
      (defn audit-trail [x y] (avg (exec-quality x y) (compliance x y)))
      (defn daily-pnl [x y] (delta (nav-impact x y) (rebal-cost x y)))))

  ;; Layer 4: 15 top-level analytics composing everything
  (define layer4
    '((defn desk-summary [x y] (blend (daily-pnl x y) (report-card x y)))
      (defn risk-report [x y] (avg (risk-alert x y) (stress-test x y)))
      (defn exec-report [x y] (blend (exec-quality x y) (audit-trail x y)))
      (defn client-report [x y] (avg (client-return x y) (report-card x y)))
      (defn monthly-attrib [x y] (blend (attrib-alpha x y) (attrib-timing x y)))
      (defn quarterly-rev [x y] (avg (perf-fee x y) (mgmt-fee x y)))
      (defn annual-review [x y] (blend (net-perf x y) (peer-rank x y)))
      (defn rebal-plan [x y] (avg (rebal-trigger x y) (order-size x y)))
      (defn compliance-chk [x y] (blend (compliance x y) (mandate-fit x y)))
      (defn hedge-plan [x y] (avg (hedge-ratio x y) (net-exp x y)))
      (defn liq-report [x y] (blend (liq-score x y) (capacity x y)))
      (defn board-deck [x y] (avg (desk-summary x y) (annual-review x y)))
      (defn reg-filing [x y] (blend (compliance-chk x y) (audit-trail x y)))
      (defn investor-letter [x y] (avg (client-report x y) (monthly-attrib x y)))
      (defn firm-pnl [x y] (blend (board-deck x y) (quarterly-rev x y)))))

  (define all (append prims layer1 layer2 layer3 layer4))
  (printf "~a functions across 5 layers\n" (length all))
  (with-output-to-file "demo-program.txt" #:exists 'replace
    (lambda ()
      (for ([fn (in-list all)]
            [i (in-naturals)])
        (when (> i 0) (printf "\n\n"))
        (define name (second fn))
        (define params (third fn))
        (define body (fourth fn))
        (printf "(defn ~a [~a]\n  ~a)"
                name
                (string-join (map symbol->string params) " ")
                (render-expr body)))))
  (printf "Written to demo-program.txt\n"))

(define (render-expr e)
  (cond
    [(number? e) (format "~a" e)]
    [(symbol? e) (symbol->string e)]
    [(list? e)
     (format "(~a ~a ~a)"
             (render-expr (first e))
             (render-expr (second e))
             (render-expr (third e)))]))

(gen)

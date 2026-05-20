#lang racket

(require cnf cnf/python)

(define python-source #<<PYTHON
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Trade:
    symbol: str
    quantity: int
    price: float
    side: str

@dataclass
class Portfolio:
    name: str
    trades: List[Trade]
    cash: float

def trade_value(trade: Trade) -> float:
    return trade.quantity * trade.price

def portfolio_value(portfolio: Portfolio) -> float:
    total = sum(trade_value(t) for t in portfolio.trades)
    return total + portfolio.cash

def trade_pnl(trade: Trade, mark_price: float) -> float:
    current = trade.quantity * mark_price
    cost = trade_value(trade)
    if trade.side == "short":
        return cost - current
    return current - cost

def portfolio_pnl(portfolio: Portfolio, marks: Dict[str, float]) -> float:
    total = 0.0
    for t in portfolio.trades:
        mark = marks.get(t.symbol, t.price)
        total += trade_pnl(t, mark)
    return total

def high_value_trades(portfolio: Portfolio, threshold: float) -> List[Trade]:
    return [t for t in portfolio.trades if trade_value(t) >= threshold]

def portfolio_summary(portfolio: Portfolio, marks: Dict[str, float]) -> Dict:
    value = portfolio_value(portfolio)
    pnl = portfolio_pnl(portfolio, marks)
    big = high_value_trades(portfolio, 10000.0)
    return {
        "name": portfolio.name,
        "value": value,
        "pnl": pnl,
        "big_trades": len(big)
    }

def risk_report(portfolios: List[Portfolio], marks: Dict[str, float]) -> List[Dict]:
    return [portfolio_summary(p, marks) for p in portfolios]
PYTHON
)

(printf "=== E14: Python Bridge Demo ===\n\n")

;; Phase 1 — Parse
(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-python-lang!)

(define t0 (current-inexact-milliseconds))
(define fns (parse-python-program! python-source))
(define t1 (current-inexact-milliseconds))

(printf "Phase 1 — Parse\n")
(printf "  Parsed ~a forms in ~a ms\n" (length fns) (~r (- t1 t0) #:precision '(= 1)))
(printf "  Objects: ~a\n" (length (all-objects)))
(printf "  Claims: ~a\n" (length (current-claims-where)))
(printf "  Forms:\n")
(for ([fn (in-list fns)])
  (define fk-claims (current-claims-where #:l fn #:p (py-form-kind-pred)))
  (define fk (and (not (null? fk-claims)) (resolve-value (list-ref (first fk-claims) 3))))
  (printf "    ~a (~a)\n" (render-ref fn) fk))

;; Phase 2 — Dependency discovery
(printf "\nPhase 2 — Dependency discovery\n")
(materialize!)
(define t2 (current-inexact-milliseconds))
(define deps (query (py-fn-depends-on (? caller) (? callee))))
(define t3 (current-inexact-milliseconds))
(printf "  py-fn-depends-on: ~a edges in ~a ms\n" (length deps) (~r (- t3 t2) #:precision '(= 1)))
(for ([d (in-list deps)])
  (printf "    ~a -> ~a\n" (render-ref (hash-ref d 'caller)) (render-ref (hash-ref d 'callee))))

;; Phase 3 — Custom rules + materialize
(printf "\nPhase 3 — Custom rules + materialize\n")
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? g)))
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? m))
  (py-trans-dep (? m) (? g)))

(define t4 (current-inexact-milliseconds))
(materialize!)
(define t5 (current-inexact-milliseconds))
(printf "  Materialize: ~a ms\n" (~r (- t5 t4) #:precision '(= 1)))
(define tdeps (query (py-trans-dep (? f) (? g))))
(define t6 (current-inexact-milliseconds))
(printf "  py-trans-dep: ~a pairs in ~a ms\n" (length tdeps) (~r (- t6 t5) #:precision '(= 1)))
(for ([d (in-list tdeps)])
  (printf "    ~a => ~a\n" (render-ref (hash-ref d 'f)) (render-ref (hash-ref d 'g))))

;; Phase 4 — Rename
(printf "\nPhase 4 — Rename\n")
(define trade-value-fn (first (filter (lambda (f) (equal? (render-ref f) "trade_value")) fns)))
(define t7 (current-inexact-milliseconds))
(void (rename! trade-value-fn "compute_trade_value"))
(define t8 (current-inexact-milliseconds))
(printf "  Renamed trade_value -> compute_trade_value in ~a ms\n"
        (~r (- t8 t7) #:precision '(= 2)))
(define callers
  (for/list ([d (in-list (query (py-fn-depends-on (? caller) (? callee))))]
             #:when (equal? (render-ref (hash-ref d 'callee)) "compute_trade_value"))
    (render-ref (hash-ref d 'caller))))
(printf "  Callers auto-updated:\n")
(for ([c (in-list callers)])
  (printf "    ~a uses compute_trade_value\n" c))

;; Phase 5 — Render
(printf "\nPhase 5 — Render (full program)\n")
(define t9 (current-inexact-milliseconds))
(define rendered (render-python-program fns))
(define t10 (current-inexact-milliseconds))
(printf "  Rendered ~a forms in ~a ms\n" (length fns) (~r (- t10 t9) #:precision '(= 1)))
(printf "\n~a\n" rendered)

;; Phase 6 — Incremental edit
(printf "\nPhase 6 — Incremental edit\n")
(define t11 (current-inexact-milliseconds))
(define new-fn
  (add-python-function! "def weighted_pnl(portfolio: Portfolio, weight: float, marks: Dict[str, float]) -> float:\n    return portfolio_pnl(portfolio, marks) * weight\n"))
(define t12 (current-inexact-milliseconds))
(printf "  add-python-function! in ~a ms\n" (~r (- t12 t11) #:precision '(= 1)))

(define t13 (current-inexact-milliseconds))
(void (modify-python-function! "compute_trade_value"
  "def net_trade_value(trade: Trade) -> float:\n    return trade.quantity * trade.price - 0.01\n"))
(define t14 (current-inexact-milliseconds))
(printf "  modify-python-function! (+ rename) in ~a ms\n" (~r (- t14 t13) #:precision '(= 1)))

(define post-deps (query (py-fn-depends-on (? caller) (? callee))))
(printf "  py-fn-depends-on after mutations: ~a edges in 0 ms\n" (length post-deps))
(for ([d (in-list post-deps)])
  (printf "    ~a -> ~a\n" (render-ref (hash-ref d 'caller)) (render-ref (hash-ref d 'callee))))

(printf "\n  Final program:\n\n")
(printf "~a\n" (render-python-program (append fns (list new-fn))))

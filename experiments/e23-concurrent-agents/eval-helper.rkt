#lang racket

(require cnf/private/kernel
         cnf/private/datalog
         (only-in cnf/private/eval
                  setup-eval! graph-eval empty-env extend-env
                  node-value node-kind node-ref
                  kind-pred run-root-pred run-status-pred
                  run-result-pred run-reason-pred run-error-node-pred
                  fuel-limit-pred fuel-used-pred)
         cnf/private/graph
         cnf/private/lang)

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)
  (materialize!))

(define args (vector->list (current-command-line-arguments)))

(define (usage!)
  (displayln "Usage:")
  (displayln "  racket eval-helper.rkt eval <file> <fn-name> <arg1> <arg2> ...")
  (displayln "  racket eval-helper.rkt deps <file>")
  (displayln "  racket eval-helper.rkt render <file>")
  (displayln "  racket eval-helper.rkt runs <file> <fn-name> <arg1> <arg2> ...")
  (exit 1))

(when (< (length args) 2) (usage!))

(define cmd (first args))
(define file (second args))
(define source (file->string file))

(fresh!)
(define fns (parse-program! source))
(materialize!)

(case cmd
  [("eval")
   (when (< (length args) 4) (usage!))
   (define fn-name (third args))
   (define fn-args (map string->number (drop args 3)))
   (define fn-id
     (for/or ([f fns])
       (and (equal? (render-ref f) fn-name) f)))
   (unless fn-id
     (fprintf (current-error-port) "Unknown function: ~a\n" fn-name)
     (exit 1))
   (define run (eval-function! fn-id fn-args))
   (define status (resolve-value (node-ref run (run-status-pred))))
   (define result-node (node-ref run (run-result-pred)))
   (define result (and result-node (node-value result-node)))
   (define reason (resolve-value (node-ref run (run-reason-pred))))
   (define fuel (resolve-value (node-ref run (fuel-used-pred))))
   (printf "status: ~a\n" status)
   (when result (printf "result: ~a\n" result))
   (when reason (printf "reason: ~a\n" reason))
   (printf "fuel: ~a\n" fuel)]

  [("deps")
   (define deps (query (fn-depends-on (? caller) (? callee))))
   (for ([d deps])
     (printf "~a -> ~a\n"
             (render-ref (hash-ref d 'caller))
             (render-ref (hash-ref d 'callee))))]

  [("render")
   (displayln (render-program fns))]

  [("runs")
   (when (< (length args) 4) (usage!))
   (define fn-name (third args))
   (define fn-args (map string->number (drop args 3)))
   (define fn-id
     (for/or ([f fns])
       (and (equal? (render-ref f) fn-name) f)))
   (unless fn-id
     (fprintf (current-error-port) "Unknown function: ~a\n" fn-name)
     (exit 1))
   (define run (eval-function! fn-id fn-args))
   (define all-runs (current-claims-where #:p (run-status-pred)))
   (printf "Total eval runs: ~a\n" (length all-runs))
   (for ([c all-runs])
     (define run-id (list-ref c 2))
     (define status (resolve-value (list-ref c 3)))
     (define root (node-ref run-id (run-root-pred)))
     (define root-name (if root (render-ref root) "?"))
     (define reason (resolve-value (node-ref run-id (run-reason-pred))))
     (printf "  ~a: ~a status=~a~a\n"
             run-id root-name status
             (if reason (format " reason=~a" reason) "")))]

  [else (usage!)])

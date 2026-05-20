#lang racket

;; MCP Server for Claim Normal Form
;;
;; Exposes CNF operations as tools over the MCP protocol (JSON-RPC 2.0 / stdio).
;; An AI agent connects via MCP and operates on the claim graph directly.

(require json
         racket/tcp
         "private/kernel.rkt"
         "private/datalog.rkt"
         "private/eval.rkt"
         "private/graph.rkt"
         "private/schema.rkt"
         "private/python.rkt")

;; Beagle bridge is optional — works without beagle-lib installed
(define beagle-available?
  (with-handlers ([exn:fail? (lambda (_) #f)])
    (dynamic-require "private/beagle.rkt" #f)
    #t))

(define-syntax-rule (beagle-ref id)
  (if beagle-available?
      (dynamic-require "private/beagle.rkt" 'id)
      (lambda args (error 'id "beagle-lib not installed"))))

(define setup-beagle-lang! (beagle-ref setup-beagle-lang!))
(define parse-beagle-program! (beagle-ref parse-beagle-program!))
(define parse-beagle-file! (beagle-ref parse-beagle-file!))
(define add-beagle-function! (beagle-ref add-beagle-function!))
(define remove-beagle-function! (beagle-ref remove-beagle-function!))
(define modify-beagle-function! (beagle-ref modify-beagle-function!))
(define render-beagle-program (beagle-ref render-beagle-program))
(define render-beagle-fn (beagle-ref render-beagle-fn))
(define form-kind-pred (beagle-ref form-kind-pred))

;; --- Transport ---

(define mcp-out (current-output-port))
(current-output-port (current-error-port))

(define (send-response msg)
  (write-json msg mcp-out)
  (write-char #\newline mcp-out)
  (flush-output mcp-out))

(define (read-message)
  (define line (read-line (current-input-port) 'any))
  (cond
    [(eof-object? line) #f]
    [(string=? line "") (read-message)]
    [else (string->jsexpr line)]))

;; --- Workspace ---

(define (init-workspace!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-schema!)
  (setup-rule-predicates!)
  (when beagle-available? (setup-beagle-lang!))
  (setup-python-lang!)
  (materialize!))

(define default-checkpoint-path
  (build-path (find-system-path 'home-dir) ".cnf" "checkpoint.json"))

;; --- Restore from checkpoint ---

(define (register-builtin-rules!)
  ;; Eval-layer rules (operand resolution, readiness, dependency tracking)
  (define-rule (operand-val (? operand) (? operand))
    (value (? operand) (? _lit)))
  (define-rule (operand-val (? operand) (? result-val))
    (current-triple (? ev) (evaluated-pred) (? operand))
    (current-triple (? ev) (result-pred) (? result-val)))
  (define-rule (ready (? expr) (? op) (? lval) (? rval))
    (current-triple (? expr) (op-pred) (? op))
    (current-triple (? expr) (left-pred) (? left))
    (current-triple (? expr) (right-pred) (? right))
    (operand-val (? left) (? lval))
    (operand-val (? right) (? rval)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (left-pred) (? dep))
    (current-triple (? dep) (op-pred) (? _op1)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (right-pred) (? dep))
    (current-triple (? dep) (op-pred) (? _op2)))
  (define-rule (affected (? x) (? changed))
    (expr-depends-on (? x) (? changed)))
  (define-rule (affected (? x) (? changed))
    (expr-depends-on (? x) (? y))
    (affected (? y) (? changed)))
  ;; Beagle-lang rules: contains-call and fn-depends-on are registered
  ;; by setup-beagle-lang! using has-child traversal
  (void))

(define (restore-workspace! data)
  (current-ctx (make-blank-ctx))
  (import-store! data)

  (define (find-pred name key)
    (define id (resolve-symbol name))
    (when id (ctx-set! key id)))

  (find-pred "op" 'op-pred)
  (find-pred "left" 'left-pred)
  (find-pred "right" 'right-pred)
  (find-pred "evaluated" 'evaluated-pred)
  (find-pred "result" 'result-pred)
  (find-pred "under-env" 'under-env-pred)
  (find-pred "name" 'name-pred)
  (find-pred "supersedes" 'supersedes-pred)
  (set-supersedes-pred! (ctx-ref 'supersedes-pred))
  (find-pred "has-param" 'has-param)
  (find-pred "position" 'position-pred)
  (find-pred "body" 'body-pred)
  (find-pred "calls" 'calls-pred)
  (find-pred "has-type" 'has-type-pred)
  (find-pred "return-type" 'return-type-pred)
  (find-pred "expr-kind" 'expr-kind-pred)
  (find-pred "has-arg" 'has-arg-pred)
  (find-pred "has-child" 'has-child-pred)
  (find-pred "has-field" 'has-field-pred)
  (find-pred "form-kind" 'form-kind-pred)
  (find-pred "is-private" 'is-private-pred)
  (find-pred "has-binding" 'has-binding-pred)
  (find-pred "binding-value" 'binding-value-pred)
  (find-pred "has-condition" 'has-condition-pred)
  (find-pred "has-then" 'has-then-pred)
  (find-pred "has-else" 'has-else-pred)
  (find-pred "rest-param" 'rest-param-pred)
  (find-pred "rule-head-rel" 'rule-head-rel-pred-id)
  (find-pred "rule-source" 'rule-source-pred-id)

  (ctx-set! 'primitives (make-hash))
  (ctx-set! 'builtins (make-hash))
  (for ([pair (list (cons "+" +) (cons "-" -) (cons "*" *) (cons "/" /))])
    (define id (resolve-symbol (car pair)))
    (when id
      (register-primitive! id (cdr pair))
      (hash-set! (ctx-ref 'builtins) (string->symbol (car pair)) id)))

  (ctx-set! 'rules '())
  (register-builtin-rules!)
  (ctx-set! 'rule-entities (make-hash))
  (restore-user-rules!)
  (materialize!))

(define (restore-user-rules!)
  (define rhrp (rule-head-rel-pred))
  (define rsp (rule-source-pred))
  (when (and rhrp rsp)
    (define head-claims (current-claims-where #:p rhrp))
    (for ([c (in-list head-claims)])
      (define rule-ent (list-ref c 2))
      (define src-claims (current-claims-where #:l rule-ent #:p rsp))
      (when (not (null? src-claims))
        (define src-str (resolve-value (list-ref (first src-claims) 3)))
        (define parts (regexp-split #rx" :- " src-str))
        (when (= (length parts) 2)
          (define head-atom (parse-atom-sexpr (read (open-input-string (first parts)))))
          (define body-atoms (parse-clauses (second parts)))
          (define rule (dl-rule head-atom body-atoms))
          (ctx-set! 'rules (cons rule (ctx-ref 'rules '())))
          (hash-set! (ctx-ref 'rule-entities) rule-ent rule))))))

;; --- S-expression query parsing ---

(define (resolve-name sym-str)
  (or (resolve-symbol sym-str)
      (let ([vid (value-id sym-str)])
        (and vid
             (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
               (and (not (null? cs))
                    (list-ref (first cs) 2)))))
      sym-str))

(define (parse-atom-sexpr sexpr)
  (define rel (car sexpr))
  (define args
    (for/list ([a (cdr sexpr)])
      (cond
        [(and (list? a) (= (length a) 2) (eq? (first a) '?))
         (var (second a))]
        [(string? a) a]
        [(number? a) a]
        [(boolean? a) a]
        [(symbol? a) (resolve-name (symbol->string a))]
        [else (error 'parse-atom "unexpected argument: ~v" a)])))
  (atom rel args))

(define (parse-clauses str)
  (define port (open-input-string str))
  (let loop ([atoms '()])
    (define sexpr (read port))
    (if (eof-object? sexpr)
        (reverse atoms)
        (loop (cons (parse-atom-sexpr sexpr) atoms)))))

;; --- Result formatting ---

(define (object-display-info id)
  (cond
    [(not (string? id)) (format "~a" id)]
    [(not (object-exists? id)) (format "~a (unknown)" id)]
    [(value-object? id)
     (format "~a (value: ~a)" id (resolve-value id))]
    [else
     (define ref (render-ref id))
     (cond
       [(not (equal? ref id))
        (format "~a (~a)" id ref)]
       [(get-claim id)
        (format "~a (claim)" id)]
       [else
        (format "~a (entity)" id)])]))

(define (format-binding v)
  (cond
    [(not (string? v)) v]
    [(value-object? v) (resolve-value v)]
    [else v]))

(define (format-results results)
  (if (null? results)
      "No results."
      (string-join
       (for/list ([s (in-list results)]
                  [i (in-naturals 1)])
         (format "~a. ~a" i
                 (string-join
                  (sort
                   (for/list ([(k v) (in-hash s)])
                     (format "?~a = ~a" k (object-display-info v)))
                   string<?)
                  ", ")))
       "\n")))

(define (format-claims claims)
  (if (null? claims)
      "No claims."
      (string-join
       (for/list ([c (in-list claims)])
         (define cid (first c))
         (define p (second c))
         (define l (third c))
         (define r (fourth c))
         (format "  ~a: (~a ~a ~a)~a"
                 cid
                 (object-display-info l)
                 (object-display-info p)
                 (object-display-info r)
                 (if (superseded? cid) " [superseded]" "")))
       "\n")))

;; --- Tool definitions ---

(define tool-defs
  (list
   ;; Core
   (hasheq
    'name "reset"
    'description "Reset workspace to fresh state with all layers initialized (eval, graph, schema, lang)."
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq
    'name "create_entity"
    'description "Create a new entity (pure referent — no properties yet). Returns the entity ID."
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq
    'name "create_named"
    'description "Create a named entity (entity + symbol claim). Returns the entity ID."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'name (hasheq 'type "string" 'description "Symbol name"))
      'required '("name")))

   (hasheq
    'name "create_value"
    'description "Create/intern a value object. Same literal always returns the same ID."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'value (hasheq 'description "Literal value (string, number, or boolean)"))
      'required '("value")))

   (hasheq
    'name "claim"
    'description "Assert a claim (left, predicate, right). Each argument is an object ID. Returns the claim ID."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'left (hasheq 'type "string" 'description "Left object ID")
        'predicate (hasheq 'type "string" 'description "Predicate object ID")
        'right (hasheq 'type "string" 'description "Right object ID"))
      'required '("left" "predicate" "right")))

   ;; Query
   (hasheq
    'name "query"
    'description (string-append
      "Run a Datalog query over the claim graph. "
      "Body uses S-expression syntax with (? name) for variables. "
      "Bare symbols resolve to named entities: (current-triple (? x) body (? b)) "
      "resolves 'body' to its predicate ID automatically. "
      "Base relations: triple(L,P,R), claim(Id,L,P,R), current-triple(L,P,R), "
      "current-claim(Id,L,P,R), value(Id,Literal), object(Id). "
      "Example: (current-triple (? fn) body (? expr))")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'body (hasheq 'type "string"
                      'description "Query body — one or more atoms in S-expression syntax"))
      'required '("body")))

   (hasheq
    'name "define_rule"
    'description (string-append
      "Define a Datalog rule (derived relation). "
      "Head and body use S-expression syntax. "
      "Bare symbols resolve to named entities automatically. "
      "Example head: (reachable (? x) (? y)), "
      "body: (current-triple (? x) body (? expr))")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'head (hasheq 'type "string" 'description "Rule head atom")
        'body (hasheq 'type "string" 'description "Rule body — one or more atoms"))
      'required '("head" "body")))

   (hasheq
    'name "list_rules"
    'description "List all rules defined as claims. Shows rule entity ID, head relation, and source."
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq
    'name "supersede_rule"
    'description "Replace a rule with a new definition. Old rule is superseded, derived facts recompute on next query."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'old_rule_id (hasheq 'type "string" 'description "Entity ID of the rule to replace")
        'head (hasheq 'type "string" 'description "New rule head atom (S-expression)")
        'body (hasheq 'type "string" 'description "New rule body atoms (S-expressions)"))
      'required '("old_rule_id" "head" "body")))

   (hasheq
    'name "inspect"
    'description "Get full information about an object: type, value/claim data, name, claims about it, claims targeting it."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'id (hasheq 'type "string" 'description "Object ID to inspect"))
      'required '("id")))

   (hasheq
    'name "resolve_symbol"
    'description "Find the entity ID for a symbol name. Returns the entity ID or null."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'name (hasheq 'type "string" 'description "Symbol name to resolve"))
      'required '("name")))

   (hasheq
    'name "claims_where"
    'description "Find claims matching optional filters on left, predicate, and/or right. Returns all claims if no filters given."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'left (hasheq 'type "string" 'description "Left object ID filter")
        'predicate (hasheq 'type "string" 'description "Predicate object ID filter")
        'right (hasheq 'type "string" 'description "Right object ID filter"))))

   ;; Schema
   (hasheq
    'name "define_predicates"
    'description "Create named predicate objects. Returns a map of name to ID."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'names (hasheq 'type "array"
                       'items (hasheq 'type "string")
                       'description "Predicate names to create"))
      'required '("names")))

   (hasheq
    'name "lookup"
    'description "Get the current value of a property on an entity. Uses supersession-aware lookup."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'entity (hasheq 'type "string" 'description "Entity ID")
        'predicate (hasheq 'type "string" 'description "Predicate ID"))
      'required '("entity" "predicate")))

   (hasheq
    'name "find_by"
    'description "Find entities that have a given property value."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'predicate (hasheq 'type "string" 'description "Predicate ID")
        'value (hasheq 'type "string" 'description "Value to match"))
      'required '("predicate" "value")))

   (hasheq
    'name "update"
    'description "Update a property value via supersession. Old value preserved as history."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'entity (hasheq 'type "string" 'description "Entity ID")
        'predicate (hasheq 'type "string" 'description "Predicate ID")
        'value (hasheq 'type "string" 'description "New value"))
      'required '("entity" "predicate" "value")))

   ;; Lang
   (hasheq
    'name "parse_program"
    'description "Parse source into the claim graph. Auto-detects language (Python or beagle). Returns entity IDs with form types. Pass language: 'python' or 'beagle' to override."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'source (hasheq 'type "string" 'description "Source text to parse")
        'language (hasheq 'type "string" 'description "Language: 'python' or 'beagle'. Auto-detected if omitted."))
      'required '("source")))

   (hasheq
    'name "render"
    'description "Render function entities back to source text."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'ids (hasheq 'type "array"
                     'items (hasheq 'type "string")
                     'description "Function entity IDs to render"))
      'required '("ids")))

   (hasheq
    'name "rename"
    'description "Rename an entity. All references (call sites, etc.) update automatically via the claim graph."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'id (hasheq 'type "string" 'description "Entity ID to rename")
        'new_name (hasheq 'type "string" 'description "New name"))
      'required '("id" "new_name")))

   (hasheq
    'name "status"
    'description "Workspace overview: object count, claim count, rule count."
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq
    'name "batch"
    'description (string-append
      "Execute multiple operations in a single call. "
      "Each operation has a 'tool' name and 'arguments' object. "
      "Operations execute sequentially; all results are returned. "
      "With atomic: true, all operations share one transaction — "
      "if any fails, all are rolled back. "
      "Example: [{\"tool\": \"define_rule\", \"arguments\": {\"head\": \"...\", \"body\": \"...\"}}, "
      "{\"tool\": \"query\", \"arguments\": {\"body\": \"...\"}}]")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'operations (hasheq
          'type "array"
          'items (hasheq
            'type "object"
            'properties (hasheq
              'tool (hasheq 'type "string" 'description "Tool name")
              'arguments (hasheq 'type "object" 'description "Tool arguments"))
            'required '("tool"))
          'description "Array of operations to execute")
        'atomic (hasheq 'type "boolean"
                        'description "If true, wrap all operations in a transaction (all-or-nothing)"))
      'required '("operations")))

   (hasheq
    'name "checkpoint"
    'description (string-append
      "Save the entire claim graph to disk. Preserves all objects, values, claims, "
      "rules, and supersession history. A subsequent restore reconstructs the full "
      "graph including materialized views — agents resume with accumulated knowledge.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'path (hasheq 'type "string"
                      'description "File path (default: ~/.cnf/checkpoint.json)"))))

   (hasheq
    'name "restore"
    'description (string-append
      "Restore a previously checkpointed claim graph. All objects, values, claims, "
      "rules, and materialized views are reconstructed. The agent resumes with full "
      "structural understanding from a prior session.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'path (hasheq 'type "string"
                      'description "File path (default: ~/.cnf/checkpoint.json)"))))

   ;; Transactions
   (hasheq
    'name "tx_log"
    'description (string-append
      "List recent transactions. Each transaction groups claims asserted together. "
      "Use since_seq to see only new transactions since a known point.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'since_seq (hasheq 'type "integer"
                           'description "Only show transactions after this sequence number (default: 0)")
        'limit (hasheq 'type "integer"
                       'description "Maximum transactions to return (default: 20)"))))

   (hasheq
    'name "current_tx_seq"
    'description (string-append
      "Return the latest transaction sequence number. Save this value, then later call "
      "tx_log with since_seq to see what changed since you last checked.")
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq
    'name "set_agent"
    'description (string-append
      "Identify this agent. All subsequent operations (claims, rules, queries) will be "
      "attributed to this agent name in the transaction log. Call once at session start.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'name (hasheq 'type "string"
                      'description "Agent identifier (e.g. 'structural-analyst', 'quality-checker')"))
      'required '("name")))

   ;; Incremental parse
   (hasheq
    'name "add_function"
    'description (string-append
      "Add a single function to the existing claim graph without reparsing. "
      "The function's claims are added incrementally and materialized views auto-update. "
      "Use this instead of reset + parse_program when adding functions to an existing graph.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'source (hasheq 'type "string"
                        'description "Beagle function definition, e.g. (defn foo [(x : Int)] : Int (+ x 1))"))
      'required '("source")))

   (hasheq
    'name "remove_function"
    'description (string-append
      "Remove a function from the claim graph by invalidating all its claims "
      "(params, body, expression tree). Materialized views auto-update — "
      "derived relations like fn-depends-on retract affected tuples.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'name (hasheq 'type "string"
                      'description "Function name to remove"))
      'required '("name")))

   (hasheq
    'name "modify_function"
    'description (string-append
      "Modify an existing function's definition in-place. The function entity is preserved "
      "(so other functions' call references still work), but params and body are replaced. "
      "Materialized views auto-update through the change — no reparse needed.")
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'name (hasheq 'type "string"
                      'description "Name of the function to modify")
        'source (hasheq 'type "string"
                        'description "New beagle function definition, e.g. (defn foo [(x : Int) (y : Int)] : Int (* x y))"))
      'required '("name" "source")))))

;; --- Resource generation ---

(define (generate-resource uri)
  (case uri
    [("cnf://summary")
     (define obj-count (length (all-objects)))
     (define claim-count (length (claims-where)))
     (define fn-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (fn-depends-on (? caller) (? callee)))))
     (define py-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (py-fn-depends-on (? caller) (? callee)))))
     (define all-deps (append fn-deps py-deps))
     (define rules
       (with-handlers ([exn:fail? (lambda (_) '())])
         (current-claims-where #:p (ctx-ref* 'rule-head-rel-pred-id))))
     (define txs (all-txs))
     (define recent-txs (if (> (length txs) 5)
                            (take-right txs 5)
                            txs))
     (string-join
      (list
       (format "=== Codebase Understanding (CNF claim graph) ===")
       (format "Objects: ~a | Claims: ~a | Dependencies: ~a"
               obj-count claim-count (length all-deps))
       (format "Rules: ~a | Transactions: ~a"
               (length rules) (length txs))
       ""
       (if (null? all-deps) "No dependencies tracked yet."
           (string-join
            (cons "Dependencies:"
                  (for/list ([d (in-list all-deps)])
                    (define ck (if (hash-has-key? d 'caller) 'caller 'caller))
                    (define callee-key (if (hash-has-key? d 'callee) 'callee 'callee))
                    (format "  ~a -> ~a"
                            (render-ref (hash-ref d ck))
                            (render-ref (hash-ref d callee-key)))))
            "\n"))
       ""
       (if (null? recent-txs) "No transactions yet."
           (string-join
            (cons "Recent transactions:"
                  (for/list ([tx (in-list recent-txs)])
                    (define seq (hash-ref tx 'seq "?"))
                    (define agent (hash-ref tx 'agent #f))
                    (define claim-count (length (hash-ref tx 'claim-ids '())))
                    (format "  tx-~a: ~a claims~a"
                            seq claim-count
                            (if agent (format " (agent: ~a)" agent) ""))))
            "\n")))
      "\n")]

    [("cnf://dependencies")
     (define fn-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (fn-depends-on (? caller) (? callee)))))
     (define py-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (py-fn-depends-on (? caller) (? callee)))))
     (define all-deps (append fn-deps py-deps))
     (if (null? all-deps)
         "No dependencies. Parse a program first."
         (string-join
          (cons (format "~a dependency edges:" (length all-deps))
                (for/list ([d (in-list all-deps)])
                  (format "  ~a -> ~a"
                          (render-ref (hash-ref d 'caller))
                          (render-ref (hash-ref d 'callee)))))
          "\n"))]

    [("cnf://functions")
     (define fn-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (fn-depends-on (? caller) (? callee)))))
     (define py-deps
       (with-handlers ([exn:fail? (lambda (_) '())])
         (query (py-fn-depends-on (? caller) (? callee)))))
     (define all-deps (append fn-deps py-deps))
     (define dep-map (make-hash))
     (for ([d all-deps])
       (define caller (hash-ref d 'caller))
       (hash-update! dep-map caller (lambda (v) (add1 v)) 0))
     (define rdep-map (make-hash))
     (for ([d all-deps])
       (define callee (hash-ref d 'callee))
       (hash-update! rdep-map callee (lambda (v) (add1 v)) 0))
     (define all-fns
       (remove-duplicates
        (append (map (lambda (d) (hash-ref d 'caller)) all-deps)
                (map (lambda (d) (hash-ref d 'callee)) all-deps))))
     (if (null? all-fns)
         "No functions indexed. Parse a program first."
         (string-join
          (cons (format "~a functions:" (length all-fns))
                (for/list ([f (in-list all-fns)])
                  (define calls-out (hash-ref dep-map f 0))
                  (define called-by (hash-ref rdep-map f 0))
                  (format "  ~a (calls: ~a, called-by: ~a)"
                          (render-ref f) calls-out called-by)))
          "\n"))]

    [("cnf://rules")
     (define rules-text
       (with-handlers ([exn:fail? (lambda (_) "No rules found.")])
         (define rule-pred (ctx-ref* 'rule-head-rel-pred-id))
         (define rule-src-pred (ctx-ref* 'rule-source-pred-id))
         (define rule-claims (current-claims-where #:p rule-pred))
         (if (null? rule-claims) "No user-defined rules."
             (string-join
              (cons (format "~a rules:" (length rule-claims))
                    (for/list ([c (in-list rule-claims)])
                      (define rule-id (list-ref c 2))
                      (define rel-name (resolve-value (list-ref c 3)))
                      (define src-claims (current-claims-where #:l rule-id #:p rule-src-pred))
                      (define src (if (null? src-claims) "?"
                                      (resolve-value (list-ref (first src-claims) 3))))
                      (format "  [~a] ~a: ~a" rule-id rel-name src)))
              "\n"))))
     rules-text]

    [else (format "Unknown resource: ~a" uri)]))

(define (ctx-ref* key)
  (ctx-ref key))

;; --- Tool handlers ---

(define (handle-tool name arguments)
  (case name
    [("reset")
     (init-workspace!)
     "Workspace reset. All layers initialized (eval, graph, schema, lang)."]

    [("create_entity")
     (define id (entity!))
     (format "Entity created: ~a" id)]

    [("create_named")
     (define n (hash-ref arguments 'name))
     (define id (named! n))
     (format "Named entity created: ~a (id: ~a)" n id)]

    [("create_value")
     (define val (hash-ref arguments 'value))
     (define id (value! val))
     (format "Value interned: ~a (id: ~a)" val id)]

    [("claim")
     (define l (hash-ref arguments 'left))
     (define p (hash-ref arguments 'predicate))
     (define r (hash-ref arguments 'right))
     (define cid (claim! l p r))
     (format "Claim created: ~a — (~a ~a ~a)" cid l p r)]

    [("query")
     (define body-str (hash-ref arguments 'body))
     (define atoms (parse-clauses body-str))
     (define results (run-query atoms))
     (format-results results)]

    [("define_rule")
     (define head-str (hash-ref arguments 'head))
     (define body-str (hash-ref arguments 'body))
     (define head-atom (parse-atom-sexpr (read (open-input-string head-str))))
     (define body-atoms (parse-clauses body-str))
     (define rule-ent (define-rule!/claims head-atom body-atoms))
     (format "Rule ~a defined: ~a :- ~a" rule-ent head-str body-str)]

    [("list_rules")
     (define rule-ents (list-rule-entities))
     (if (null? rule-ents)
         "No rules defined as claims."
         (string-join
          (cons (format "~a rule(s):" (length rule-ents))
                (for/list ([ent (in-list rule-ents)])
                  (define head-claims
                    (current-claims-where #:l ent #:p (rule-head-rel-pred)))
                  (define head-rel
                    (if (null? head-claims) "?"
                        (resolve-value (list-ref (first head-claims) 3))))
                  (define src-claims
                    (current-claims-where #:l ent #:p (rule-source-pred)))
                  (define src
                    (if (null? src-claims) "?"
                        (resolve-value (list-ref (first src-claims) 3))))
                  (format "  ~a: ~a — ~a" ent head-rel src)))
          "\n"))]

    [("supersede_rule")
     (define old-id (hash-ref arguments 'old_rule_id))
     (define head-str (hash-ref arguments 'head))
     (define body-str (hash-ref arguments 'body))
     (define head-atom (parse-atom-sexpr (read (open-input-string head-str))))
     (define body-atoms (parse-clauses body-str))
     (define new-ent (supersede-rule! old-id head-atom body-atoms))
     (format "Rule ~a superseded by ~a: ~a :- ~a" old-id new-ent head-str body-str)]

    [("inspect")
     (define id (hash-ref arguments 'id))
     (cond
       [(not (object-exists? id))
        (format "Object ~a does not exist." id)]
       [else
        (define lines '())
        (define (add! s) (set! lines (cons s lines)))

        (add! (format "Object: ~a" id))

        (cond
          [(value-object? id)
           (add! (format "Type: value"))
           (add! (format "Literal: ~a" (resolve-value id)))]
          [(get-claim id)
           => (lambda (c)
                (add! (format "Type: claim"))
                (add! (format "Left: ~a" (object-display-info (first c))))
                (add! (format "Predicate: ~a" (object-display-info (second c))))
                (add! (format "Right: ~a" (object-display-info (third c))))
                (when (superseded? id)
                  (add! "Status: SUPERSEDED")))]
          [else
           (add! "Type: entity")])

        (define ref (render-ref id))
        (unless (equal? ref id)
          (add! (format "Name: ~a" ref)))

        (define about (claims-about id))
        (unless (null? about)
          (add! (format "Claims about (~a):" (length about)))
          (for ([c (in-list about)])
            (define cid (first c))
            (define p (second c))
            (define r (third c))
            (add! (format "  ~a ~a ~a~a"
                          cid
                          (object-display-info p)
                          (object-display-info r)
                          (if (superseded? cid) " [superseded]" "")))))

        (define targeting (claims-targeting id))
        (unless (null? targeting)
          (add! (format "Claims targeting (~a):" (length targeting)))
          (for ([c (in-list targeting)])
            (define cid (first c))
            (define p (second c))
            (define from (third c))
            (add! (format "  ~a ~a ~a~a"
                          cid
                          (object-display-info p)
                          (object-display-info from)
                          (if (superseded? cid) " [superseded]" "")))))

        (string-join (reverse lines) "\n")])]

    [("resolve_symbol")
     (define n (hash-ref arguments 'name))
     (define id (resolve-symbol n))
     (if id
         (format "~a -> ~a" n id)
         (format "Symbol '~a' not found." n))]

    [("claims_where")
     (define l (hash-ref arguments 'left #f))
     (define p (hash-ref arguments 'predicate #f))
     (define r (hash-ref arguments 'right #f))
     (define cs (claims-where #:l l #:p p #:r r))
     (if (null? cs)
         "No claims found."
         (format "~a claims:\n~a" (length cs) (format-claims cs)))]

    [("define_predicates")
     (define names (hash-ref arguments 'names))
     (define pairs
       (for/list ([n (in-list names)])
         (define id (named! n))
         (cons n id)))
     (string-join
      (cons "Predicates created:"
            (for/list ([p (in-list pairs)])
              (format "  ~a: ~a" (car p) (cdr p))))
      "\n")]

    [("lookup")
     (define ent (hash-ref arguments 'entity))
     (define pred (hash-ref arguments 'predicate))
     (define val (lookup ent pred))
     (if val
         (format "~a" val)
         "No current value.")]

    [("find_by")
     (define pred (hash-ref arguments 'predicate))
     (define val (hash-ref arguments 'value))
     (define ids (find-by pred val))
     (if (null? ids)
         "No entities found."
         (format "Found ~a: ~a" (length ids) (string-join ids ", ")))]

    [("update")
     (define ent (hash-ref arguments 'entity))
     (define pred (hash-ref arguments 'predicate))
     (define val (hash-ref arguments 'value))
     (define cid (update! ent pred val))
     (format "Updated. New claim: ~a" cid)]

    [("parse_program")
     (define source (hash-ref arguments 'source))
     (define lang-override (hash-ref arguments 'language #f))
     (define lang
       (or lang-override
           (if (or (regexp-match? #rx"^\\s*def " source)
                   (regexp-match? #rx"^\\s*class " source)
                   (regexp-match? #rx"^\\s*import " source)
                   (regexp-match? #rx"^\\s*from " source))
               "python" "beagle")))
     (define fns
       (if (equal? lang "python")
           (parse-python-program! source)
           (parse-beagle-program! source)))
     (define fk-pred
       (if (equal? lang "python") (py-form-kind-pred) (form-kind-pred)))
     (define form-lines
       (for/list ([f (in-list fns)])
         (define kind-cs (current-claims-where #:l f #:p fk-pred))
         (define kind (and (not (null? kind-cs))
                          (resolve-value (list-ref (first kind-cs) 3))))
         (format "  ~a: ~a (~a)" f (render-ref f) (or kind "?"))))
     (define obj-count (length (all-objects)))
     (define claim-count (length (claims-where)))
     (define dep-relation
       (if (equal? lang "python") "py-fn-depends-on" "fn-depends-on"))
     (string-join
      (append
       (list (format "Parsed ~a form(s) [~a] (~a objects, ~a claims):"
                     (length fns) lang obj-count claim-count))
       form-lines
       (list ""
             (format "Dependency relation: ~a(caller, callee)" dep-relation)
             "Use query tool with this relation to discover cross-function dependencies."
             ""
             "Resources available (inject into context):"
             "  cnf://summary — codebase overview + deps + recent changes"
             "  cnf://dependencies — full dependency graph"
             "  cnf://functions — function index with call counts"
             "  cnf://rules — all Datalog rules"))
      "\n")]

    [("render")
     (define ids (hash-ref arguments 'ids))
     (define first-id (first ids))
     (define fk-claims (current-claims-where #:l first-id #:p (py-form-kind-pred)))
     (define is-python (not (null? fk-claims)))
     (if is-python
         (if (= (length ids) 1)
             (render-python-fn first-id)
             (render-python-program ids))
         (if (= (length ids) 1)
             (render-beagle-fn first-id)
             (render-beagle-program ids)))]

    [("rename")
     (define id (hash-ref arguments 'id))
     (define new-name (hash-ref arguments 'new_name))
     (rename! id new-name)
     (format "Renamed ~a to '~a'. All references updated." id new-name)]

    [("status")
     (define objs (length (all-objects)))
     (define cls (length (claims-where)))
     (define rules (length (ctx-ref 'rules '())))
     (define rule-ents (length (list-rule-entities)))
     (define tx-count (length (all-txs)))
     (define latest-seq (current-tx-seq))
     (format "Objects: ~a\nClaims: ~a\nRules: ~a (~a as claims)\nTransactions: ~a (latest seq: ~a)"
             objs cls rules rule-ents tx-count latest-seq)]

    [("batch")
     (define ops (hash-ref arguments 'operations))
     (define atomic? (hash-ref arguments 'atomic #f))
     (define (execute-batch)
       (for/list ([op (in-list ops)]
                  [i (in-naturals 1)])
         (define tool-name (hash-ref op 'tool))
         (define tool-args (hash-ref op 'arguments (hasheq)))
         (define-values (result is-error)
           (with-handlers ([exn:fail? (lambda (e)
                             (values (exn-message e) #t))])
             (values (handle-tool tool-name tool-args) #f)))
         (when (and is-error atomic?)
           (error 'batch "operation ~a (~a) failed: ~a" i tool-name result))
         (if is-error
             (format "[~a] ~a ERROR: ~a" i tool-name result)
             (format "[~a] ~a:\n~a" i tool-name result))))
     (define results
       (if atomic?
           (call-with-transaction (lambda () (execute-batch))
                                  #:agent (ctx-ref 'current-agent #f))
           (execute-batch)))
     (string-join results "\n\n")]

    [("checkpoint")
     (define path (hash-ref arguments 'path (path->string default-checkpoint-path)))
     (define dir (path-only path))
     (when (and dir (not (directory-exists? dir)))
       (make-directory* dir))
     (define data (export-store))
     (call-with-output-file path #:exists 'replace
       (lambda (out) (write-json data out)))
     (format "Checkpoint saved: ~a (~a objects, ~a claims)"
             path (length (hash-ref data 'objects)) (length (hash-ref data 'claims)))]

    [("restore")
     (define path (hash-ref arguments 'path (path->string default-checkpoint-path)))
     (unless (file-exists? path)
       (error 'restore "checkpoint not found: ~a" path))
     (define data (call-with-input-file path read-json))
     (restore-workspace! data)
     (define rule-count (length (ctx-ref 'rules '())))
     (define user-rules (length (list-rule-entities)))
     (define tx-count (length (all-txs)))
     (define latest-seq (current-tx-seq))
     (format "Restored from ~a (~a objects, ~a claims, ~a rules [~a builtin, ~a user], ~a txs [latest seq ~a])"
             path (length (all-objects)) (length (claims-where))
             rule-count (- rule-count user-rules) user-rules
             tx-count latest-seq)]

    [("tx_log")
     (define since (hash-ref arguments 'since_seq 0))
     (define limit (hash-ref arguments 'limit 20))
     (define txs (all-txs))
     (define filtered (filter (lambda (tx) (> (tx-seq tx) since)) txs))
     (define limited (if (<= (length filtered) limit)
                         filtered
                         (take filtered limit)))
     (if (null? limited)
         "No transactions."
         (string-join
          (cons (format "~a transaction(s)~a:"
                        (length limited)
                        (if (> since 0) (format " (since seq ~a)" since) ""))
                (for/list ([tx (in-list limited)])
                  (define seq (tx-seq tx))
                  (define agent (tx-agent tx))
                  (define cids (tx-claims tx))
                  (format "  tx ~a (seq ~a~a): ~a claim(s)"
                          tx seq
                          (if agent (format ", agent: ~a" agent) "")
                          (length cids))))
          "\n"))]

    [("current_tx_seq")
     (format "~a" (current-tx-seq))]

    [("set_agent")
     (define agent-name (hash-ref arguments 'name))
     (ctx-set! 'current-agent agent-name)
     (format "Agent identity set to '~a'. All subsequent operations will be attributed to this agent." agent-name)]

    [("add_function")
     (define source (hash-ref arguments 'source))
     (define lang (hash-ref arguments 'language #f))
     (define is-python (or (equal? lang "python")
                          (and (not lang) (regexp-match? #rx"^\\s*def " source))))
     (define fn-id
       (if is-python (add-python-function! source) (add-beagle-function! source)))
     (define fn-name (render-ref fn-id))
     (define obj-count (length (all-objects)))
     (define claim-count (length (claims-where)))
     (format "Added function ~a (id: ~a). Graph: ~a objects, ~a claims."
             fn-name fn-id obj-count claim-count)]

    [("remove_function")
     (define fn-name (hash-ref arguments 'name))
     (define fn-id
       (let ([resolved (resolve-symbol fn-name)])
         (cond
           [(not resolved) (error 'remove_function "unknown function: ~a" fn-name)]
           [(not (null? (current-claims-where #:l resolved #:p (py-form-kind-pred))))
            (remove-python-function! fn-name)]
           [beagle-available?
            (remove-beagle-function! fn-name)]
           [else (error 'remove_function "cannot determine language for: ~a" fn-name)])))
     (define obj-count (length (all-objects)))
     (define claim-count (length (claims-where)))
     (format "Removed function ~a (id: ~a). Claims invalidated. Graph: ~a objects, ~a claims."
             fn-name fn-id obj-count claim-count)]

    [("modify_function")
     (define fn-name (hash-ref arguments 'name))
     (define source (hash-ref arguments 'source))
     (define lang (hash-ref arguments 'language #f))
     (define is-python (or (equal? lang "python")
                          (and (not lang) (regexp-match? #rx"^\\s*def " source))))
     (define fn-id
       (if is-python
           (modify-python-function! fn-name source)
           (modify-beagle-function! fn-name source)))
     (define new-name (render-ref fn-id))
     (define obj-count (length (all-objects)))
     (define claim-count (length (claims-where)))
     (format "Modified function ~a~a (id: ~a). Graph: ~a objects, ~a claims."
             fn-name
             (if (equal? fn-name new-name) "" (format " → ~a" new-name))
             fn-id obj-count claim-count)]

    [else
     (error 'handle-tool "Unknown tool: ~a" name)]))

;; --- JSON-RPC dispatch (transport-independent) ---

(define (make-response msg)
  (define method (hash-ref msg 'method #f))
  (define id (hash-ref msg 'id #f))
  (define params (hash-ref msg 'params (hasheq)))

  (case method
    [("initialize")
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq
               'protocolVersion "2024-11-05"
               'capabilities (hasheq 'tools (hasheq)
                                    'resources (hasheq))
               'serverInfo (hasheq 'name "cnf-server"
                                   'version "0.2.0")))]

    [("notifications/initialized") #f]

    [("ping")
     (hasheq 'jsonrpc "2.0" 'id id 'result (hasheq))]

    [("resources/list")
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq 'resources
               (list
                (hasheq 'uri "cnf://summary"
                        'name "Codebase Summary"
                        'description "High-level overview: function count, dependencies, rules, recent changes. Inject into agent context for persistent memory."
                        'mimeType "text/plain")
                (hasheq 'uri "cnf://dependencies"
                        'name "Dependency Graph"
                        'description "All fn-depends-on edges. The agent's structural understanding of the codebase."
                        'mimeType "text/plain")
                (hasheq 'uri "cnf://functions"
                        'name "Function Index"
                        'description "All functions with types, params, and dependency counts."
                        'mimeType "text/plain")
                (hasheq 'uri "cnf://rules"
                        'name "Datalog Rules"
                        'description "All defined rules (built-in and user-defined). Shows accumulated agent understanding."
                        'mimeType "text/plain"))))]

    [("resources/read")
     (define uri (hash-ref params 'uri ""))
     (define content (generate-resource uri))
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq 'contents
               (list (hasheq 'uri uri
                             'mimeType "text/plain"
                             'text content))))]

    [("tools/list")
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq 'tools tool-defs))]

    [("tools/call")
     (define tool-name (hash-ref params 'name))
     (define arguments (hash-ref params 'arguments (hasheq)))
     (define-values (result is-error)
       (with-handlers ([exn:fail? (lambda (e)
                         (values (exn-message e) #t))])
         (values (handle-tool tool-name arguments) #f)))
     (define text (if (string? result) result (format "~a" result)))
     (hasheq 'jsonrpc "2.0"
             'id id
             'result
             (let ([content (list (hasheq 'type "text" 'text text))])
               (if is-error
                   (hasheq 'content content 'isError #t)
                   (hasheq 'content content))))]

    [else
     (and id
          (hasheq 'jsonrpc "2.0"
                  'id id
                  'error (hasheq 'code -32601
                                 'message (format "Unknown method: ~a" method))))]))

;; --- MVCC (snapshot isolation for reads, serialized writes) ---

(define read-only-tools
  '("query" "inspect" "resolve_symbol" "claims_where" "find_by"
    "lookup" "render" "status" "list_rules" "tx_log" "current_tx_seq"))

(define (read-only-tool? name)
  (member name read-only-tools))

;; --- Daemon mode (TCP, shared state, multi-client) ---

(define (run-daemon port-num)
  (define listener (tcp-listen port-num 5 #t))
  (eprintf "cnf-daemon: listening on port ~a (MVCC)\n" port-num)
  (define write-sem (make-semaphore 1))
  (define committed (box (snapshot-ctx)))

  (let accept-loop ()
    (define-values (in out) (tcp-accept listener))
    (eprintf "cnf-daemon: client connected\n")
    (thread
     (lambda ()
       (with-handlers ([exn:fail? (lambda (e)
                         (eprintf "cnf-daemon: client error: ~a\n" (exn-message e)))])
         (let loop ()
           (define line (read-line in 'any))
           (cond
             [(eof-object? line)
              (eprintf "cnf-daemon: client disconnected\n")]
             [(string=? line "") (loop)]
             [else
              (define msg (string->jsexpr line))
              (define tool-name
                (and (equal? (hash-ref msg 'method #f) "tools/call")
                     (hash-ref (hash-ref msg 'params (hasheq)) 'name #f)))
              (if (and tool-name (read-only-tool? tool-name))
                  (parameterize ([current-ctx (unbox committed)])
                    (define response (make-response msg))
                    (when response
                      (write-json response out)
                      (write-char #\newline out)
                      (flush-output out)))
                  (call-with-semaphore write-sem
                    (lambda ()
                      (define response (make-response msg))
                      (when response
                        (write-json response out)
                        (write-char #\newline out)
                        (flush-output out))
                      (set-box! committed (snapshot-ctx)))))
              (loop)])))
       (close-input-port in)
       (close-output-port out)))
    (accept-loop)))

;; --- Bridge mode (stdio ↔ TCP proxy for Claude Code) ---

(define (run-bridge port-num)
  (define-values (tcp-in tcp-out) (tcp-connect "127.0.0.1" port-num))
  (eprintf "cnf-bridge: connected to daemon on port ~a\n" port-num)

  (thread
   (lambda ()
     (let loop ()
       (define line (read-line tcp-in 'any))
       (cond
         [(eof-object? line)
          (eprintf "cnf-bridge: daemon disconnected\n")]
         [else
          (write-string line mcp-out)
          (write-char #\newline mcp-out)
          (flush-output mcp-out)
          (loop)]))))

  (let loop ()
    (define line (read-line (current-input-port) 'any))
    (cond
      [(eof-object? line)
       (close-output-port tcp-out)
       (close-input-port tcp-in)]
      [(string=? line "") (loop)]
      [else
       (write-string line tcp-out)
       (write-char #\newline tcp-out)
       (flush-output tcp-out)
       (loop)])))

;; --- Main ---

(define args (current-command-line-arguments))

(let ([mode (and (>= (vector-length args) 1) (vector-ref args 0))]
      [arg2 (and (>= (vector-length args) 2) (vector-ref args 1))])
  (cond
    ;; Daemon mode: TCP server, auto-restores from checkpoint
    [(equal? mode "--daemon")
     (let ([port-num (string->number arg2)])
       (if (file-exists? default-checkpoint-path)
           (let ([data (call-with-input-file default-checkpoint-path read-json)])
             (restore-workspace! data)
             (eprintf "cnf-daemon: restored (~a objects, ~a claims)\n"
                      (length (all-objects)) (length (claims-where))))
           (init-workspace!))
       (run-daemon port-num))]

    ;; Bridge mode: stdio proxy to running daemon
    [(equal? mode "--connect")
     (run-bridge (string->number arg2))]

    ;; Standard stdio mode
    [else
     (init-workspace!)
     (eprintf "cnf-server: ready\n")
     (let loop ()
       (let ([msg (read-message)])
         (when msg
           (with-handlers ([exn:fail? (lambda (e)
                             (eprintf "cnf-server error: ~a\n" (exn-message e)))])
             (let ([response (make-response msg)])
               (when response (send-response response))))
           (loop))))]))

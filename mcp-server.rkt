#lang racket

;; MCP Server for Claim Normal Form
;;
;; Exposes CNF operations as tools over the MCP protocol (JSON-RPC 2.0 / stdio).
;; An AI agent connects via MCP and operates on the claim graph directly.

(require json
         "cnf.rkt"
         "datalog.rkt"
         "eval.rkt"
         "graph.rkt"
         "schema.rkt"
         "lang.rkt")

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
  (setup-lang!)
  (materialize!))

;; --- S-expression query parsing ---

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
        [(symbol? a) (symbol->string a)]
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
      "Base relations: triple(L,P,R), claim(Id,L,P,R), current-triple(L,P,R), "
      "current-claim(Id,L,P,R), value(Id,Literal), object(Id). "
      "Example: (current-triple (? x) \"42\" (? r))")
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
      "Example head: (reachable (? x) (? y)), "
      "body: (triple (? x) \"edge-pred-id\" (? y))")
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
    'description "Parse source text (CNF mini-language) into the claim graph. Returns function entity IDs."
    'inputSchema (hasheq
      'type "object"
      'properties (hasheq
        'source (hasheq 'type "string" 'description "Source text to parse"))
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
    'inputSchema (hasheq 'type "object" 'properties (hasheq)))))

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
     (define fns (parse-program! source))
     (string-join
      (cons (format "Parsed ~a function(s):" (length fns))
            (for/list ([f (in-list fns)])
              (format "  ~a: ~a" f (render-ref f))))
      "\n")]

    [("render")
     (define ids (hash-ref arguments 'ids))
     (if (= (length ids) 1)
         (render-fn (first ids))
         (render-program ids))]

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
     (format "Objects: ~a\nClaims: ~a\nRules: ~a (~a as claims)" objs cls rules rule-ents)]

    [else
     (error 'handle-tool "Unknown tool: ~a" name)]))

;; --- JSON-RPC dispatch ---

(define (handle-request msg)
  (define method (hash-ref msg 'method #f))
  (define id (hash-ref msg 'id #f))
  (define params (hash-ref msg 'params (hasheq)))

  (case method
    [("initialize")
     (send-response
      (hasheq 'jsonrpc "2.0"
              'id id
              'result (hasheq
                'protocolVersion "2024-11-05"
                'capabilities (hasheq 'tools (hasheq))
                'serverInfo (hasheq 'name "cnf-server"
                                    'version "0.1.0"))))]

    [("notifications/initialized") (void)]

    [("ping")
     (send-response (hasheq 'jsonrpc "2.0" 'id id 'result (hasheq)))]

    [("tools/list")
     (send-response
      (hasheq 'jsonrpc "2.0"
              'id id
              'result (hasheq 'tools tool-defs)))]

    [("tools/call")
     (define tool-name (hash-ref params 'name))
     (define arguments (hash-ref params 'arguments (hasheq)))
     (define-values (result is-error)
       (with-handlers ([exn:fail? (lambda (e)
                         (values (exn-message e) #t))])
         (values (handle-tool tool-name arguments) #f)))
     (define text (if (string? result) result (format "~a" result)))
     (send-response
      (hasheq 'jsonrpc "2.0"
              'id id
              'result
              (let ([content (list (hasheq 'type "text" 'text text))])
                (if is-error
                    (hasheq 'content content 'isError #t)
                    (hasheq 'content content)))))]

    [else
     (when id
       (send-response
        (hasheq 'jsonrpc "2.0"
                'id id
                'error (hasheq 'code -32601
                               'message (format "Unknown method: ~a" method)))))]))

;; --- Main ---

(init-workspace!)
(eprintf "cnf-server: ready\n")

(let loop ()
  (define msg (read-message))
  (when msg
    (with-handlers ([exn:fail? (lambda (e)
                      (eprintf "cnf-server error: ~a\n" (exn-message e)))])
      (handle-request msg))
    (loop)))

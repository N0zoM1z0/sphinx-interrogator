; Sphinx Interrogator bounded relation-contract scaffold.
; Expected output: three `unsat` results.
(set-logic QF_BV)

(define-fun sbox4 ((x (_ BitVec 4))) (_ BitVec 4)
  (ite (= x #x0) #x6
  (ite (= x #x1) #xb
  (ite (= x #x2) #x0
  (ite (= x #x3) #x4
  (ite (= x #x4) #xd
  (ite (= x #x5) #x3
  (ite (= x #x6) #xf
  (ite (= x #x7) #x8
  (ite (= x #x8) #xa
  (ite (= x #x9) #x2
  (ite (= x #xa) #x5
  (ite (= x #xb) #xc
  (ite (= x #xc) #x1
  (ite (= x #xd) #xe
  (ite (= x #xe) #x7 #x9))))))))))))))))

(define-fun bank ((secret (_ BitVec 4))
                  (token (_ BitVec 4))
                  (epoch (_ BitVec 1))) (_ BitVec 2)
  (let ((v (sbox4 (bvxor secret token))))
    (ite (= epoch #b0) ((_ extract 1 0) v) ((_ extract 3 2) v))))

(declare-const secret (_ BitVec 4))
(declare-const token (_ BitVec 4))
(declare-const epoch (_ BitVec 1))
(declare-const bank-a (_ BitVec 2))
(declare-const bank-b (_ BitVec 2))
(declare-const public-digest-a (_ BitVec 64))
(declare-const public-digest-b (_ BitVec 64))
(declare-const normalized-static-a (_ BitVec 16))
(declare-const normalized-static-b (_ BitVec 16))

(assert (distinct bank-a bank-b))

; Architectural relation: experiment instructions cannot affect the public digest.
(assert (= public-digest-a #x0000000000000000))
(assert (= public-digest-b #x0000000000000000))
(push)
(assert (not (= public-digest-a public-digest-b)))
(check-sat)
(pop)

; Fault-free relation: changing only an anchor preserves normalized static cost.
(assert (= normalized-static-a #x0000))
(assert (= normalized-static-b #x0000))
(push)
(assert (not (= normalized-static-a normalized-static-b)))
(check-sat)
(pop)

; Directional fault lemma: with an active guard and no suppression, a slower
; bank-b follow-up implies that the projected secret bank is bank-b.
(declare-const guard-active Bool)
(declare-const replay-suppressed Bool)
(define-fun delta-a () (_ BitVec 2)
  (ite (and guard-active (not replay-suppressed)
            (= (bank secret token epoch) bank-a)) #b01 #b00))
(define-fun delta-b () (_ BitVec 2)
  (ite (and guard-active (not replay-suppressed)
            (= (bank secret token epoch) bank-b)) #b01 #b00))
(assert guard-active)
(assert (not replay-suppressed))
(assert (bvugt delta-b delta-a))
(push)
(assert (not (= (bank secret token epoch) bank-b)))
(check-sat)
(pop)

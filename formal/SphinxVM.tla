------------------------------ MODULE SphinxVM ------------------------------
EXTENDS Naturals, FiniteSets, TLC

CONSTANTS Lanes, Tokens, Epochs, Banks, FaultEnabled

ASSUME /\ Lanes # {}
       /\ Tokens # {}
       /\ Epochs = {0, 1}
       /\ Banks = {0, 1, 2, 3}

VARIABLES phase,
          replayCredit,
          lastBank,
          pendingBank,
          pendingEpoch,
          pendingGuard,
          faultCycles

vars == <<phase, replayCredit, lastBank, pendingBank, pendingEpoch,
          pendingGuard, faultCycles>>

None == -1

(* A small public stand-in for the concrete secret bank function. The production
   model replaces this operator with the bit-vector S-box definition. *)
BankOf(lane, token, epoch) == (lane + token + (2 * epoch)) % 4

GuardOf(lane, token, epoch) ==
    phase = ((lane + token + epoch) % 4)

Init ==
    /\ phase = 0
    /\ replayCredit = 0
    /\ lastBank = None
    /\ pendingBank = None
    /\ pendingEpoch = None
    /\ pendingGuard = FALSE
    /\ faultCycles = 0

Probe(lane, token, epoch) ==
    /\ lane \in Lanes
    /\ token \in Tokens
    /\ epoch \in Epochs
    /\ pendingBank' = BankOf(lane, token, epoch)
    /\ pendingEpoch' = epoch
    /\ pendingGuard' = GuardOf(lane, token, epoch)
    /\ phase' = (phase + 1 + epoch) % 4
    /\ UNCHANGED <<replayCredit, lastBank, faultCycles>>

Anchor(bank, epoch) ==
    LET matched == pendingBank # None /\ pendingEpoch = epoch
        collision == matched /\ pendingBank = bank
        delta == IF FaultEnabled /\ collision /\ pendingGuard /\ replayCredit # 3
                 THEN 1 ELSE 0
    IN /\ bank \in Banks
       /\ epoch \in Epochs
       /\ faultCycles' = faultCycles + delta
       /\ replayCredit' = IF matched
                            THEN IF collision
                                 THEN IF replayCredit = 3 THEN 3 ELSE replayCredit + 1
                                 ELSE IF replayCredit = 0 THEN 0 ELSE replayCredit - 1
                            ELSE replayCredit
       /\ lastBank' = IF matched THEN pendingBank ELSE lastBank
       /\ pendingBank' = None
       /\ pendingEpoch' = None
       /\ pendingGuard' = FALSE
       /\ UNCHANGED phase

Pad(amount) ==
    /\ amount \in 0..3
    /\ phase' = (phase + amount) % 4
    /\ UNCHANGED <<replayCredit, lastBank, pendingBank, pendingEpoch,
                    pendingGuard, faultCycles>>

Fence ==
    /\ replayCredit' = 0
    /\ pendingBank' = None
    /\ pendingEpoch' = None
    /\ pendingGuard' = FALSE
    /\ UNCHANGED <<phase, lastBank, faultCycles>>

HardReset == Init'

SoftReset ==
    /\ pendingBank' = None
    /\ pendingEpoch' = None
    /\ pendingGuard' = FALSE
    /\ UNCHANGED <<phase, replayCredit, lastBank, faultCycles>>

Next ==
    \/ \E lane \in Lanes, token \in Tokens, epoch \in Epochs:
          Probe(lane, token, epoch)
    \/ \E bank \in Banks, epoch \in Epochs: Anchor(bank, epoch)
    \/ \E amount \in 0..3: Pad(amount)
    \/ Fence
    \/ HardReset
    \/ SoftReset

TypeOK ==
    /\ phase \in 0..3
    /\ replayCredit \in 0..3
    /\ lastBank \in Banks \cup {None}
    /\ pendingBank \in Banks \cup {None}
    /\ pendingEpoch \in Epochs \cup {None}
    /\ pendingGuard \in BOOLEAN
    /\ faultCycles \in Nat

NoFaultMeansZero == ~FaultEnabled => faultCycles = 0

Spec == Init /\ [][Next]_vars

=============================================================================

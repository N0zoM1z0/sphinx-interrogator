------------------------------ MODULE SphinxVM ------------------------------
EXTENDS Integers, FiniteSets, TLC

CONSTANTS Lanes, Tokens, Epochs, Banks, FaultEnabled, SoftPreserved, MaxGas

ASSUME /\ Lanes # {}
       /\ Tokens # {}
       /\ Epochs = {0, 1}
       /\ Banks = {0, 1, 2, 3}

VARIABLES phase,
          replayCredit,
          lastBank,
          uopCacheTag,
          uopCacheValid,
          pendingBank,
          pendingEpoch,
          pendingGuard,
          faultCycles,
          archDigest,
          gas,
          retired,
          staticCost

vars == <<phase, replayCredit, lastBank, uopCacheTag, uopCacheValid,
          pendingBank, pendingEpoch, pendingGuard, faultCycles,
          archDigest, gas, retired, staticCost>>

None == -1

(* A small public stand-in for the concrete secret bank function. The production
   model replaces this operator with the bit-vector S-box definition. *)
BankOf(lane, token, epoch) == (lane + token + (2 * epoch)) % 4

Xor2(a, b) == (((a % 2) + (b % 2)) % 2)
              + (2 * ((((a \div 2) % 2) + ((b \div 2) % 2)) % 2))

GuardOf(lane, token, epoch) ==
    phase = Xor2(Xor2(lane % 4, token % 4), epoch)

Init ==
    /\ phase = 0
    /\ replayCredit = 0
    /\ lastBank = None
    /\ uopCacheTag = 0
    /\ uopCacheValid = FALSE
    /\ pendingBank = None
    /\ pendingEpoch = None
    /\ pendingGuard = FALSE
    /\ faultCycles = 0
    /\ archDigest = 0
    /\ gas = MaxGas
    /\ retired = 0
    /\ staticCost = 0

Probe(lane, token, epoch) ==
    /\ gas > 0
    /\ lane \in Lanes
    /\ token \in Tokens
    /\ epoch \in Epochs
    /\ pendingBank' = BankOf(lane, token, epoch)
    /\ pendingEpoch' = epoch
    /\ pendingGuard' = GuardOf(lane, token, epoch)
    /\ phase' = (phase + 1 + epoch) % 4
    /\ uopCacheTag' = 12
    /\ uopCacheValid' = TRUE
    /\ gas' = gas - 1
    /\ retired' = retired + 1
    /\ staticCost' = staticCost + 5
    /\ archDigest' = archDigest
    /\ UNCHANGED <<replayCredit, lastBank, faultCycles>>

Anchor(bank, epoch) ==
    LET matched == pendingBank # None /\ pendingEpoch = epoch
        collision == matched /\ pendingBank = bank
        delta == IF FaultEnabled /\ collision /\ pendingGuard /\ replayCredit # 3
                 THEN 1 ELSE 0
    IN /\ gas > 0
       /\ bank \in Banks
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
       /\ uopCacheTag' = 13
       /\ uopCacheValid' = TRUE
       /\ gas' = gas - 1
       /\ retired' = retired + 1
       /\ staticCost' = staticCost + 4
       /\ archDigest' = archDigest
       /\ UNCHANGED phase

Pad(amount) ==
    /\ gas > 0
    /\ amount \in 0..3
    /\ phase' = (phase + amount) % 4
    /\ uopCacheTag' = 14
    /\ uopCacheValid' = TRUE
    /\ gas' = gas - 1
    /\ retired' = retired + 1
    /\ staticCost' = staticCost + amount
    /\ archDigest' = archDigest
    /\ UNCHANGED <<replayCredit, lastBank, pendingBank, pendingEpoch,
                    pendingGuard, faultCycles>>

Fence ==
    /\ gas > 0
    /\ replayCredit' = 0
    /\ pendingBank' = None
    /\ pendingEpoch' = None
    /\ pendingGuard' = FALSE
    /\ uopCacheTag' = 15
    /\ uopCacheValid' = TRUE
    /\ gas' = gas - 1
    /\ retired' = retired + 1
    /\ staticCost' = staticCost + 2
    /\ archDigest' = archDigest
    /\ UNCHANGED <<phase, lastBank, faultCycles>>

HardReset ==
    /\ phase' = 0
    /\ replayCredit' = 0
    /\ lastBank' = None
    /\ uopCacheTag' = 0
    /\ uopCacheValid' = FALSE
    /\ pendingBank' = None
    /\ pendingEpoch' = None
    /\ pendingGuard' = FALSE
    /\ faultCycles' = 0
    /\ archDigest' = 0
    /\ gas' = MaxGas
    /\ retired' = 0
    /\ staticCost' = 0

SoftReset ==
    /\ phase' = IF "phase" \in SoftPreserved THEN phase ELSE 0
    /\ lastBank' = IF "lastBank" \in SoftPreserved THEN lastBank ELSE None
    /\ replayCredit' = IF "replayCredit" \in SoftPreserved THEN replayCredit ELSE 0
    /\ uopCacheTag' = IF "uopCache" \in SoftPreserved THEN uopCacheTag ELSE 0
    /\ uopCacheValid' = IF "uopCache" \in SoftPreserved THEN uopCacheValid ELSE FALSE
    /\ pendingBank' = None
    /\ pendingEpoch' = None
    /\ pendingGuard' = FALSE
    /\ archDigest' = archDigest
    /\ gas' = MaxGas
    /\ retired' = 0
    /\ staticCost' = 0
    /\ UNCHANGED faultCycles

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
    /\ uopCacheTag \in 0..15
    /\ uopCacheValid \in BOOLEAN
    /\ pendingBank \in Banks \cup {None}
    /\ pendingEpoch \in Epochs \cup {None}
    /\ pendingGuard \in BOOLEAN
    /\ faultCycles \in Nat
    /\ archDigest \in Nat
    /\ gas \in 0..MaxGas
    /\ retired \in 0..MaxGas
    /\ staticCost \in Nat

NoFaultMeansZero == ~FaultEnabled => faultCycles = 0
ExperimentArchConfinement == archDigest = 0
GasProgress == gas + retired = MaxGas
NormalizedCostInvariant == ~FaultEnabled => staticCost + faultCycles = staticCost

Spec == Init /\ [][Next]_vars

=============================================================================

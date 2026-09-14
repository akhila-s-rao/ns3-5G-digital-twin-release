# Custom NR Regression Tests

## Purpose

This report lists the automated NR test coverage added on top of the checked-in
5G-LENA release. These tests protect the custom SR/BSR recovery, UL MCS limiting,
bootstrap-grant, scheduler-lookahead, and Expeca-style TDD timing behavior.

## New Test Suite: UE MAC SR/BSR Behavior

Source: `contrib/nr/test/nr-test-ue-mac-retx-bsr.cc`

Test suite: `nr-ue-mac-retx-bsr`

The test verifies that:

- new buffered data at an idle UE requests an immediate SR;
- restarting `RetxBsrTimer` postpones its expiry;
- timer expiry requests a recovery SR when data remains buffered;
- emptying the buffer cancels the timer and returns the UE to `INACTIVE`;
- disabling SR periodicity preserves immediate-SR behavior;
- configured SR periodicity and offset select the expected SR opportunities; and
- separate UEs retain independent SR offsets.

The source is registered in `contrib/nr/CMakeLists.txt`. The test file and that
CMake registration must be committed together so that the suite is compiled and
run by the ns-3 test framework.

## Added Scheduler Tests

Source: `contrib/nr/test/nr-test-sched.cc`

### UL MCS Limit

`TestUlMcsLimit()` verifies that:

- `MaxUlMcs = -1` leaves UL MCS limiting disabled;
- MCS values above the configured limit are capped;
- MCS values below the limit remain unchanged;
- newly registered UE scheduler state respects the limit;
- changing the limit caps existing UE state; and
- UL CQI expiry does not restore an MCS above the configured limit.

### Bootstrap and Recovery SR Classification

`TestSrBootstrapClassification()` verifies that:

- a recovery SR preserves an existing positive gNB UL-buffer estimate;
- a recovery SR does not activate the bootstrap MCS cap;
- an SR with a zero gNB buffer estimate is classified as bootstrap;
- a bootstrap SR seeds the synthetic UL-buffer estimate;
- bootstrap MCS is capped at 9;
- an RBG size of one still produces an exact five-PRB bootstrap grant;
- repeated bootstrap SRs preserve pending bootstrap state until grant creation; and
- releasing a UE clears its pending bootstrap state.

## Added Pattern and Lookahead Tests

Source: `contrib/nr/test/nr-lte-pattern-generation.cc`

The additions verify that:

- `UlSchedulerLookaheadSlots = 6` is stored and returned correctly; and
- the `DL|DL|DL|F|UL` Expeca-style pattern, UL scheduler lookahead, and K2 setting
  produce the expected scheduler-invocation and UL-DCI transmission maps.

## Additional Runtime Validation

The Expeca-style flexible-slot symbol restrictions were also checked with short
simulation runs. Those checks confirmed three UL allocation symbols and five DL
allocation symbols in an `F` slot, full-slot UL operation in the `UL` slot, and
SRS placement only in full UL slots. These smoke checks are not currently a
separate permanent unit-test suite.

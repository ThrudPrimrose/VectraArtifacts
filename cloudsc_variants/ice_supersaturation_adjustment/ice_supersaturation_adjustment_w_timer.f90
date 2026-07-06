SUBROUTINE ice_supersaturation_adjustment( KIDIA, KFDIA, KLON, &
    ZTP1, ZA, ZQX_NCLDQV, ZQSICE, ZCORQSICE, ZFOKOOP, &
    ZSOLQA, ZSOLAC, ZQXFG, &
    RTT, RAMIN, RTHOMO, NSSOPT, RKOOPTAU, PTSPHY, ZEPSEC, &
    NCLDQL, NCLDQI, NCLDQV, NCLV, TIMER ) BIND(C, NAME="ice_supersaturation_adjustment")
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: c_int, c_double, c_bool
  IMPLICIT NONE
  integer(8) :: start, finish, count_rate, count_max
  real(8) :: elapsed_time
  

  REAL(c_double), INTENT(OUT)   :: TIMER(2)

  ! Dimensions
  INTEGER(c_int), VALUE :: KIDIA, KFDIA, KLON
  INTEGER(c_int), VALUE :: NCLV
  INTEGER(c_int), VALUE :: NCLDQL, NCLDQI, NCLDQV
  INTEGER(c_int), VALUE :: NSSOPT

  ! Input arrays (1D over JL = 1..KLON)
  REAL(c_double), INTENT(IN) :: ZTP1(KLON)
  REAL(c_double), INTENT(IN) :: ZA(KLON)
  REAL(c_double), INTENT(IN) :: ZQX_NCLDQV(KLON)
  REAL(c_double), INTENT(IN) :: ZQSICE(KLON)
  REAL(c_double), INTENT(IN) :: ZCORQSICE(KLON)
  REAL(c_double), INTENT(IN) :: ZFOKOOP(KLON)

  ! Constants
  REAL(c_double), VALUE :: RTT, RAMIN, RTHOMO, RKOOPTAU, PTSPHY, ZEPSEC

  ! Output/InOut arrays
  REAL(c_double), INTENT(INOUT) :: ZSOLQA(KLON, NCLV, NCLV)
  REAL(c_double), INTENT(INOUT) :: ZSOLAC(KLON)
  REAL(c_double), INTENT(INOUT) :: ZQXFG(KLON, NCLV)

  ! Local variables
  INTEGER(c_int) :: JL
  REAL(c_double) :: ZFAC, ZFACI
  REAL(c_double) :: ZSUPSAT, ZQP1ENV
  REAL(c_double) :: ZEPSILON
  ! Get the clock rate (counts per second)
  call system_clock(count_rate=count_rate, count_max=count_max)
  
  ! Start timing
  call system_clock(start)

  ZEPSILON = 1.0D-14

  DO JL = 1, KLON

    IF (ZTP1(JL) >= RTT .OR. NSSOPT == 0_c_int) THEN
      ZFAC  = 1.0D0
      ZFACI = 1.0D0
    ELSE
      ZFAC  = ZA(JL) + ZFOKOOP(JL) * (1.0D0 - ZA(JL))
      ZFACI = PTSPHY / RKOOPTAU
    ENDIF

    IF (ZA(JL) > 1.0D0 - RAMIN) THEN
      ZSUPSAT = MAX((ZQX_NCLDQV(JL) - ZFAC * ZQSICE(JL)) / ZCORQSICE(JL), 0.0D0)
    ELSE
      ZQP1ENV = (ZQX_NCLDQV(JL) - ZA(JL) * ZQSICE(JL)) / &
                MAX(1.0D0 - ZA(JL), ZEPSILON)
      ZSUPSAT = MAX((1.0D0 - ZA(JL)) * (ZQP1ENV - ZFAC * ZQSICE(JL)) / &
                    ZCORQSICE(JL), 0.0D0)
    ENDIF

    IF (ZSUPSAT > ZEPSEC) THEN

      IF (ZTP1(JL) > RTHOMO) THEN
        ZSOLQA(JL, NCLDQL, NCLDQV) = ZSOLQA(JL, NCLDQL, NCLDQV) + ZSUPSAT
        ZSOLQA(JL, NCLDQV, NCLDQL) = ZSOLQA(JL, NCLDQV, NCLDQL) - ZSUPSAT
        ZQXFG(JL, NCLDQL) = ZQXFG(JL, NCLDQL) + ZSUPSAT
      ELSE
        ZSOLQA(JL, NCLDQI, NCLDQV) = ZSOLQA(JL, NCLDQI, NCLDQV) + ZSUPSAT
        ZSOLQA(JL, NCLDQV, NCLDQI) = ZSOLQA(JL, NCLDQV, NCLDQI) - ZSUPSAT
        ZQXFG(JL, NCLDQI) = ZQXFG(JL, NCLDQI) + ZSUPSAT
      ENDIF

      ZSOLAC(JL) = (1.0D0 - ZA(JL)) * ZFACI

    ENDIF

  ENDDO
  ! Stop timing
  call system_clock(finish)
  
  ! Calculate elapsed time in seconds
  elapsed_time = real(finish - start, 8) / real(count_rate, 8)
  ! Print results
  print *, 'Elapsed time (seconds):', elapsed_time
  print *, 'Elapsed time (nanoseconds):', elapsed_time * 1.0e9
  print *, 'Clock resolution (nanoseconds):', 1.0e9 / real(count_rate, 8)
  timer(1) = elapsed_time * 1.0e6

END SUBROUTINE ice_supersaturation_adjustment

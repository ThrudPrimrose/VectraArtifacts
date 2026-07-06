SUBROUTINE autoconversion_snow( KIDIA, KFDIA, KLON, &
    ZTP1, ZICECLD, PNICE, &
    ZSOLQB, ZSNOWAUT, &
    RTT, RLCRITSNOW, RSNOWLIN1, RSNOWLIN2, RNICE, &
    PTSPHY, ZEPSEC, LAERICEAUTO, NCLDQS, NCLDQI, TIMER) BIND(C, NAME="autoconversion_snow")
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: c_int, c_double, c_bool
  IMPLICIT NONE
  
  integer(8) :: start, finish, count_rate, count_max
  real(8) :: elapsed_time
  

  REAL(c_double), INTENT(OUT)   :: TIMER(2)

  ! Dimensions / indices (scalars passed by value)
  INTEGER(c_int), VALUE :: KIDIA, KFDIA, KLON
  INTEGER(c_int), VALUE :: NCLDQS, NCLDQI
  
  ! Input arrays (1D over JL = 1..KFDIA)
  REAL(c_double), INTENT(IN) :: ZTP1(KLON)      ! Temperature
  REAL(c_double), INTENT(IN) :: ZICECLD(KLON)   ! Ice cloud water
  REAL(c_double), INTENT(IN) :: PNICE(KLON)     ! Ice number concentration
  
  ! Constants (scalars passed by value)
  REAL(c_double), VALUE :: RTT              ! Triple point temperature
  REAL(c_double), VALUE :: RLCRITSNOW       ! Critical ice content for snow
  REAL(c_double), VALUE :: RSNOWLIN1        ! Linear autoconversion coefficient 1
  REAL(c_double), VALUE :: RSNOWLIN2        ! Linear autoconversion coefficient 2
  REAL(c_double), VALUE :: RNICE            ! Reference ice number concentration
  REAL(c_double), VALUE :: PTSPHY           ! Time step
  REAL(c_double), VALUE :: ZEPSEC           ! Small epsilon
  LOGICAL(c_bool), VALUE :: LAERICEAUTO     ! Aerosol-aware ice autoconversion
  
  ! Output arrays
  REAL(c_double), INTENT(OUT)   :: ZSNOWAUT(KLON)                 ! Snow autoconversion
  REAL(c_double), INTENT(INOUT) :: ZSOLQB(KLON, NCLDQS, NCLDQI)   ! Source/sink terms
  
  ! Local variables
  INTEGER(c_int)   :: JL
  REAL(c_double)   :: ZZCO, ZLCRIT
  ! Get the clock rate (counts per second)
  call system_clock(count_rate=count_rate, count_max=count_max)
  
  ! Start timing
  call system_clock(start)
  
  ! Initialize output
  ZSNOWAUT(:) = 0.0D0
  
  ! Main computation loop
  DO JL = 1, KLON
 
    IF (ZTP1(JL) <= RTT) THEN
      IF (ZICECLD(JL) > ZEPSEC) THEN

        ZZCO = PTSPHY * RSNOWLIN1 * EXP(RSNOWLIN2 * (ZTP1(JL) - RTT))

        IF (LAERICEAUTO) THEN
          ZLCRIT = RLCRITSNOW
          ZZCO   = ZZCO * (RNICE / PNICE(JL))**0.333D0
        ELSE
          ZLCRIT = RLCRITSNOW
        END IF

        ZSNOWAUT(JL) = ZZCO * (1.0D0 - EXP(-(ZICECLD(JL) / ZLCRIT)**2))
        ZSOLQB(JL, NCLDQS, NCLDQI) = ZSOLQB(JL, NCLDQS, NCLDQI) + ZSNOWAUT(JL)

      END IF
    END IF 
  
  END DO

  ! Stop timing
  call system_clock(finish)
  
  ! Calculate elapsed time in seconds
  elapsed_time = real(finish - start, 8) / real(count_rate, 8)
  ! Print results
  print *, 'Elapsed time (seconds):', elapsed_time
  print *, 'Elapsed time (nanoseconds):', elapsed_time * 1.0e9
  print *, 'Clock resolution (nanoseconds):', 1.0e9 / real(count_rate, 8)
  timer(1) = elapsed_time * 1.0e6
END SUBROUTINE autoconversion_snow

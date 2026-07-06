SUBROUTINE lu_solver_microphysics( KIDIA, KFDIA, KLON, NCLV, ZQLHS, ZQXN, TIMER ) BIND(C, NAME="lu_solver_microphysics")
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: c_int, c_double
  IMPLICIT NONE

  integer(8) :: start, finish, count_rate, count_max
  real(8) :: elapsed_time
  

  REAL(c_double), INTENT(OUT)   :: TIMER(2)

  ! Dimensions (scalars passed by value)
  INTEGER(c_int), VALUE :: KIDIA, KFDIA, KLON, NCLV
  
  ! InOut arrays
  REAL(c_double), INTENT(INOUT) :: ZQLHS(KLON, NCLV, NCLV)
  REAL(c_double), INTENT(INOUT) :: ZQXN(KLON, NCLV)
  
  ! Local variables
  INTEGER(c_int) :: JL, JN, JM, IK
  ! Get the clock rate (counts per second)
  call system_clock(count_rate=count_rate, count_max=count_max)
  
  ! Start timing
  call system_clock(start)


  ! LU factorization (per column JL)
  DO JN = 1, NCLV - 1  
    DO JM = JN + 1, NCLV 

      DO JL = 1, KLON
        ZQLHS(JL, JM, JN) = ZQLHS(JL, JM, JN) / ZQLHS(JL, JN, JN)
      END DO
 
      DO IK = JN + 1, NCLV
        DO JL = 1, KLON
          ZQLHS(JL, JM, IK) = ZQLHS(JL, JM, IK) - (ZQLHS(JL, JM, JN) * ZQLHS(JL, JN, IK))
        END DO
      END DO
    END DO
  END DO        

  ! Forward substitution
  DO JN = 2, NCLV
    DO JM = 1, JN - 1
      DO JL = 1, KLON
        ZQXN(JL, JN) = ZQXN(JL, JN) - (ZQLHS(JL, JN, JM) * ZQXN(JL, JM))
      END DO
    END DO
  END DO

  ! Backward substitution: last variable
  DO JL = 1, KLON
    ZQXN(JL, NCLV) = ZQXN(JL, NCLV) / ZQLHS(JL, NCLV, NCLV)
  END DO
  
  ! Backward substitution: remaining variables
  DO JN = NCLV - 1, 1, -1
    DO JM = JN + 1, NCLV
      ! adds error
      DO JL = 1, KLON
        ZQXN(JL, JN) = ZQXN(JL, JN) - (ZQLHS(JL, JN, JM) * ZQXN(JL, JM))
      END DO
    END DO
    DO JL = 1, KLON
      ZQXN(JL, JN) = ZQXN(JL, JN) / ZQLHS(JL, JN, JN)
    END DO
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
END SUBROUTINE lu_solver_microphysics
C     ==================================================================
C     EXAMPLE4 -- driver for the genuine 1975-era RKF45 integrator.
C     Solves Y'=-Y, Y(0)=1 and compares the answer with EXP(-T).
C     D1MACH supplies the host-library constant required by RKF45.
C     ==================================================================
      PROGRAM ODEDEM
      DOUBLE PRECISION Y(1),WORK(9),T,TOUT,RELERR,ABSERR,EXACT
      INTEGER IWORK(5),IFLAG,K
      EXTERNAL DERIV
      Y(1)=1.0D0
      T=0.0D0
      RELERR=1.0D-8
      ABSERR=1.0D-10
      IFLAG=1
      WRITE(6,10)
   10 FORMAT(5X,1HT,12X,7HRKF45 Y,9X,7HEXACT Y,9X,5HERROR)
      DO 20 K=1,4
      TOUT=0.25D0*FLOAT(K)
      CALL RKF45(DERIV,1,Y,T,TOUT,RELERR,ABSERR,IFLAG,
     1           WORK,IWORK)
      IF (IFLAG .NE. 2) GO TO 90
      EXACT=DEXP(-T)
      WRITE(6,30) T,Y(1),EXACT,DABS(Y(1)-EXACT)
   20 CONTINUE
   30 FORMAT(1X,F8.4,3D16.7)
      STOP
   90 WRITE(6,100) IFLAG
  100 FORMAT(16H RKF45 FAILURE ,I4)
      END

      SUBROUTINE DERIV(T,Y,YP)
      DOUBLE PRECISION T,Y(1),YP(1)
      YP(1)=-Y(1)
      RETURN
      END

      DOUBLE PRECISION FUNCTION D1MACH(I)
C     D1MACH(4): largest relative spacing for IEEE double precision.
      INTEGER I
      D1MACH=2.220446049250313D-16
      RETURN
      END

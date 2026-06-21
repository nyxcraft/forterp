C     ==================================================================
C     EXAMPLE2 -- driver for the genuine 1978 LINPACK routines.
C     Solves A*X=B with DGEFA and DGESL.  The exact solution is 1,-2,-2.
C     ==================================================================
      PROGRAM LINSOL
      DOUBLE PRECISION A(3,3), B(3)
      INTEGER IPVT(3), INFO, I
      DATA A /3D0,2D0,-1D0,2D0,-2D0,0.5D0,
     1       -1D0,4D0,-1D0/
      DATA B /1D0,-2D0,0D0/
      CALL DGEFA(A,3,3,IPVT,INFO)
      WRITE(6,10) INFO
   10 FORMAT(7H INFO =,I3)
      IF (INFO .NE. 0) STOP
      CALL DGESL(A,3,3,IPVT,B,0)
      WRITE(6,20) (B(I),I=1,3)
   20 FORMAT(11H SOLUTION: ,3F12.6)
      END

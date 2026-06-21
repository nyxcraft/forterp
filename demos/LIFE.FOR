      IMPLICIT INTEGER (A-Z)
      COMMON Q,ST,IT,D(6400)
      INTEGER R(80)
      DATA BL,BIT/' ','O'/
      Q=80
      QQ=Q*Q
      DO 1 I=1,QQ
    1 D(I)=0
      ST=9999
      Q2=Q/2
      READ(5,8) CY,PI,I
    8 FORMAT(3I5)
    5 READ(5,9,END=11) R
    9 FORMAT(80A1)
      DO 10 K=1,Q
      IF(R(K).EQ.BL) GO TO 10
      L=I*Q+K-1
      D(L)=ST
      ST=L
   10 CONTINUE
      I=I+1
      GO TO 5
   11 WRITE(6,3)
    3 FORMAT('1')
      IT=0
      CALL PRT
      DO 4 IT=1,CY
      CALL NEXGEN(&6)
    4 IF(MOD(IT,PI).EQ.0) CALL PRT
      GO TO 2
    6 WRITE(6,7) IT
    7 FORMAT(' DIED AT ITERATION ',I4)
    2 STOP
      END

      SUBROUTINE PRT
      IMPLICIT INTEGER (A-Z)
      COMMON Q,ST,IT,D(1)
      INTEGER P(80)
      DATA BL,BIT/' ','O'/
      U=0
      L=10000
      B=0
      A=10000
      K=ST
   22 IF(K.EQ.9999) GO TO 21
      J=MOD(K-1,Q)
      IF(J.GT.B) B=J
      IF(J.LT.A) A=J
      IF(K.GT.U) U=K
      IF(K.LT.L) L=K
      K=D(K)
      GO TO 22
   21 WRITE(6,23) IT
   23 FORMAT(//' GENERATION:',I5)
      WRITE(6,28)
   28 FORMAT(4X,'.........1.........2.........3.........4.........5
     1.........6.........7.........8')
      U=(U-1)/Q
      L=(L-1)/Q
      DO 27 K=1,Q
   27 P(K)=BL
      DO 24 I=L,U
      DO 25 J=A,B
      P(J)=BL
   25 IF(D(I*Q+J+1).NE.0) P(J)=BIT
   24 WRITE(6,26) I,P,I
   26 FORMAT(1X,I3,80A1,I2)
      WRITE(6,28)
      RETURN
      END

      SUBROUTINE NEXGEN(*)
      IMPLICIT INTEGER (A-Z)
      COMMON Q,ST,IT,D(1)
      INTEGER NK(8),NNK(8)
      NB=-9999
      BB=NB
      K=ST
    1 IF(K.EQ.9999) GO TO 6
      CALL NEIBR(K,NK,&13)
      NN=0
      DO 2 I=1,8
      NKI=NK(I)
      IF(D(NKI).LE.0) GO TO 3
      NN=NN+1
      GO TO 2
    3 IF(D(NKI).LT.0) GO TO 2
      CALL NEIBR(NKI,NNK,&13)
      NNN=0
      DO 4 J=1,8
    4 IF(D(NNK(J)).GT.0) NNN=NNN+1
      IF(NNN.NE.3) GO TO 5
      D(NKI)=NB
      NB=-NKI
      GO TO 2
    5 D(NKI)=BB
      BB=-NKI
    2 CONTINUE
      IF(NN.EQ.2.OR.NN.EQ.3) GO TO 12
   13 D(K)=D(K)+10000
      K=D(K)-10000
      GO TO 1
   12 K=D(K)
      GO TO 1
    6 CONTINUE
   16 IF(ST.EQ.9999) RETURN 1
      IF(D(ST).LT.10000) GO TO 14
      I=ST
      ST=D(ST)-10000
      D(I)=0
      GO TO 16
   14 K=D(ST)
      DK=ST
   15 IF(K.EQ.9999) GO TO 11
      IF(D(K).LT.10000) GO TO 20
      D(DK)=D(K)-10000
      D(K)=0
      K=D(DK)
      GO TO 15
   20 DK=K
      K=D(K)
      GO TO 15
   11 IF(NB.EQ.-9999) GO TO 17
      K=-NB
    8 IF(K.EQ.9999) GO TO 7
      D(K)=-D(K)
      CK=K
      K=D(K)
      GO TO 8
    7 D(CK)=ST
      ST=-NB
   17 K=-BB
    9 IF(K.EQ.9999) RETURN
      I=K
      K=-D(K)
      D(I)=0
      GO TO 9
      END

      SUBROUTINE NEIBR(K,NK,*)
      IMPLICIT INTEGER (A-Z)
      COMMON Q
      INTEGER NK(8)
      Q1=Q-1
      K1=K-1
      I=K1/Q
      J=MOD(K1,Q)
      IF(I.EQ.0.OR.I.EQ.Q1.OR.J.EQ.0.OR.J.EQ.Q1) RETURN 1
      NK(1)=K1
      NK(2)=K1+2
      NK(3)=K1+Q
      NK(4)=NK(3)+1
      NK(5)=NK(4)+1
      NK(6)=K1-Q
      NK(7)=NK(6)+1
      NK(8)=NK(7)+1
      RETURN
      END

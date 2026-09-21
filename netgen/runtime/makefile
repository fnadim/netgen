CC=gcc
OBJ=runcell.o numtools.o derivs.o inf_tau.o

all: runcell

runcell: $(OBJ)
	$(CC) -o runcell $(OBJ) -lm

runcell.o: defs.h numtools.h runcell.c 
numtools.o: numtools.h numtools.c
derivs.o: defs.h prototypes.h derivs.c
inf_tau.o: inf_tau.c

clean: 
	/bin/rm -f *.o

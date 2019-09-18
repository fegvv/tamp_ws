// NO ROS INCLUDES HERE

#pragma once

#include <eigen3/Eigen/Eigen>
#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <iomanip>
#include <cstring>
#include <cstdlib>
#include <cmath>

using namespace std;

// acado codegen
#include "acado_common.h"
#include "acado_auxiliary_functions.h"

// util
#include "planning_util.h"
#include <common/interp.h>
#include "common/cpp_utils.h"

// define variables
#define NX         ACADO_NX	/* number of differential states */
#define NXA        ACADO_NXA	/* number of alg. states */
#define NU         ACADO_NU	/* number of control inputs */
#define N          ACADO_N	/* number of control intervals */
#define NY	       ACADO_NY	/* number of references, nodes 0..N - 1 */
#define NYN	       ACADO_NYN
#define NOD        ACADO_NOD
#define NUM_STEPS  100		/* number of simulation steps */
#define VERBOSE    1		/* show iterations: 1, silent: 0 */

ACADOvariables acadoVariables;
ACADOworkspace acadoWorkspace;

class RtisqpWrapper
{
public:

    // constructors
    RtisqpWrapper();

    // functions
    bool setWeights(std::vector<double>, std::vector<double>, double);
    bool setInitialGuess(planning_util::trajstruct);
    bool setInitialState(planning_util::statestruct);
    bool setOptReference(planning_util::trajstruct, planning_util::refstruct refs);
    bool setInputConstraints(double mu, double Fzf);
    planning_util::posconstrstruct setStateConstraints(planning_util::trajstruct &traj,
                                                       planning_util::obstastruct obs,
                                                       std::vector<float> lld,
                                                       std::vector<float> rld);
    bool shiftStateAndControls();
    bool shiftTrajectoryFwdSimple(planning_util::trajstruct &traj);
    bool doPreparationStep();
    int  doFeedbackStep();
    Eigen::MatrixXd getStateTrajectory();
    Eigen::MatrixXd getControlTrajectory();
    planning_util::trajstruct getTrajectory();
    bool computeTrajset(std::vector<planning_util::trajstruct> &trajset,
                        planning_util::statestruct &state,
                        planning_util::pathstruct &pathlocal,
                        uint Ntrajs);
};

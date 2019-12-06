#!/usr/bin/env python

# Node description:
# translate trajstar into specific control inputs for the vehicle
# runs at 100 Hz

import numpy as np
import rospy
from common.msg import Trajectory
from common.msg import Path
from common.msg import State
from fssim_common.msg import Cmd
from fssim_common.msg import State as fssimState
from visualization_msgs.msg import Marker
from std_msgs.msg import Float32
from coordinate_transforms import ptsCartesianToFrenet
from coordinate_transforms import ptsFrenetToCartesian
class CtrlInterface:
    def __init__(self):
        
        # params
        self.robot_name = rospy.get_param('/robot_name')
        
        # init node subs pubs
        rospy.init_node('ctrl_interface', anonymous=True)
        self.trajstarsub = rospy.Subscriber("trajstar", Trajectory, self.trajstar_callback)
        self.pathlocalsub = rospy.Subscriber("pathlocal", Path, self.pathlocal_callback)
        self.vehicle_out_sub = rospy.Subscriber("/fssim/base_pose_ground_truth", fssimState, self.vehicle_out_callback)
        self.vehicleinpub = rospy.Publisher('/fssim/cmd', Cmd, queue_size=10)
        self.lhptpub = rospy.Publisher('/lhpt_vis', Marker, queue_size=1)
        self.vx_errorpub = rospy.Publisher('/vx_error_vis', Float32, queue_size=1)
        self.rate = rospy.Rate(100)

        # set static vehicle params
        self.setStaticParams()

        # init msgs
        self.state = State()
        self.vehicle_in = Cmd()
        self.trajstar = Trajectory()
        self.pathlocal = Path()
        self.trajstar_received = False
        self.pathlocal_received = False
        self.state_received = False
        
        # ctrl errors
        self.vx_error = Float32()

        # TODO GET FROM MESSAGE
        # mode in state machine 
        # 0: stop
        # 1: cruise_ctrl
        # 2: tamp 
        self.ctrl_mode = 1
        
        # TODO GET FROM PARAM
        self.cc_vxref = 15
        self.cc_dref = -1.75        
        
        # delay sim variable
        self.delta_out_FIFO = []

        # wait for messages before entering main loop
        while(not self.state_received):
            print("waiting for state")
            self.rate.sleep()

        # main loop
        while not rospy.is_shutdown(): 

            if(self.ctrl_mode == 0):     # STOP
                print "stopped state, zero ctrl input"
                delta_out = 0
                dc_out = 0
            elif(self.ctrl_mode == 1):   # CRUISE CTRL             
                while(not self.pathlocal_received):
                    print("waiting for pathlocal")
                    self.rate.sleep()
                delta_out, dc_out, Xlh,Ylh = self.cc_ctrl()           
                           
            elif(self.ctrl_mode == 2):   # TAMP   
                while(not self.trajstar_received):
                    print("waiting for trajstar")
                    self.rate.sleep()         
                delta_out, dc_out, Xlh, Ylh = self.tamp_ctrl()
            else:
                print "invalid ctrl_mode! ctrl_mode = ", self.ctrl_mode
    
            # publish ctrl cmd            
            self.vehicle_in.delta = delta_out
            self.vehicle_in.dc = dc_out
            self.vehicleinpub.publish(self.vehicle_in)

            # publish tuning info
            self.vx_errorpub.publish(self.vx_error)
            if (self.ctrl_mode in [1,2]):
                m = self.getlhptmarker(Xlh,Ylh)
                self.lhptpub.publish(m)
            self.rate.sleep()
    
    def cc_ctrl(self):
        # get lhpt
        lhdist = 7 # todo determine from velocity
        s_lh = self.state.s + lhdist
        d_lh = self.cc_dref
        
        Xlh, Ylh = ptsFrenetToCartesian(np.array(s_lh), \
                                        np.array(d_lh), \
                                        np.array(self.pathlocal.X), \
                                        np.array(self.pathlocal.Y), \
                                        np.array(self.pathlocal.psi_c), \
                                        np.array(self.pathlocal.s))
        
        rho_pp = self.pp_curvature(self.state.X,self.state.Y,self.state.psi,Xlh,Ylh)
        delta_out = rho_pp*(self.lf + self.lr) # kinematic feed fwd
        
        self.vx_error = self.cc_vxref - self.state.vx
        if(self.robot_name == "gotthard"):
            k = 500
        else: 
            k = 1 # todo tune for rhino
        dc_out = k*self.vx_error
        return delta_out, dc_out, Xlh,Ylh
        
        
    def tamp_ctrl(self):
        
        # LATERAL CTRL
        # feedfwd        
        # compute local curvature of trajhat (rho)
        lhpt_idx = 5;
        Xlh = self.trajstar.X[lhpt_idx]
        Ylh = self.trajstar.Y[lhpt_idx]
        rho_pp = self.pp_curvature(self.trajstar.X[0],
                                   self.trajstar.Y[0],
                                   self.trajstar.psi[0],
                                   Xlh,
                                   Ylh)
        
        # feedback
        # todo add feedback from yawrate

        # compute control
        delta_out = rho_pp*(self.lf + self.lr) # kinematic feed fwd

        # LONGITUDINAL CTRL
        # feedfwd
        Fx_request = self.trajstar.Fxf[0] + self.trajstar.Fxr[0]
            
        if(self.robot_name == "gotthard"):
            # feedfwd 
            Cr0 = 180
            Cm1 = 5000          
            dc_out = (Fx_request+Cr0)/Cm1 # not including aero
        else:
            dc_out = Fx_request
        
        # feedback (todo)
        self.vx_error = self.trajstar.vx[1]-self.state.vx
        
        return delta_out, dc_out, Xlh, Ylh

    def pp_curvature(self,Xego,Yego,psiego,Xlh,Ylh):
        deltaX = (Xlh-Xego)
        deltaY = (Ylh-Yego)
        lh_dist = np.sqrt(deltaX**2 + deltaY**2)
        lh_angle = np.arctan2(deltaY,deltaX) - psiego
        #print "lh_angle = ", lh_angle
        rho_pp = 2*np.sin(lh_angle)/lh_dist     
        return rho_pp

    def menger_curvature(self,x0,y0,x1,y1,x2,y2):
        signedarea = (x0*(y1-y2) + x1*(y2-y0) + x2*(y0-y1))/2.0
        d0 = np.sqrt((x0-x1)**2 + (y0-y1)**2)
        d1 = np.sqrt((x1-x2)**2 + (y1-y2)**2)
        d2 = np.sqrt((x2-x0)**2 + (y2-y0)**2)
        rho_mn = 4.0*signedarea/(d0*d1*d2)
        return rho_mn

#    shift = 1 # compensate for actuator delay
#    rho_menger = self.menger_curvature(self.trajstar.X[0+shift],
#                                       self.trajstar.Y[0+shift],
#                                       self.trajstar.X[1+shift],
#                                       self.trajstar.Y[1+shift],
#                                       self.trajstar.X[2+shift],
#                                       self.trajstar.Y[2+shift])


    def getlhptmarker(self,Xlh,Ylh):
        m = Marker()
        m.header.stamp = rospy.Time.now()
        m.header.frame_id = "map"
        m.pose.position.x = Xlh;
        m.pose.position.y = Ylh;
        m.pose.position.z = 0.1;
        m.type = m.SPHERE;
        m.scale.x = 0.6;
        m.scale.y = 0.6;
        m.scale.z = 0.6;
        m.color.a = 1.0; 
        m.color.r = 0.0;
        m.color.g = 0.0;
        m.color.b = 1.0;
        return m

    def trajstar_callback(self, msg):
        self.trajstar = msg
        self.trajstar_received = True
  
    def pathlocal_callback(self, msg):
        self.pathlocal = msg
        self.pathlocal_received = True
    
    def vehicle_out_callback(self, msg):
        self.state.X = msg.x
        self.state.Y = msg.y
        self.state.psi = msg.yaw
        self.state.psidot = msg.r
        self.state.vx = msg.vx
        self.state.vy = msg.vy
        
        while(not self.pathlocal_received):
            print("waiting for pathlocal")
            self.rate.sleep()
        self.state.s,self.state.d = ptsCartesianToFrenet(np.array(self.state.X), \
                                                         np.array(self.state.Y), \
                                                         np.array(self.pathlocal.X), \
                                                         np.array(self.pathlocal.Y), \
                                                         np.array(self.pathlocal.psi_c), \
                                                         np.array(self.pathlocal.s))
        
        self.state_received = True

    def setStaticParams(self):
        self.lf = rospy.get_param('/car/kinematics/b_F')
        self.lr = rospy.get_param('/car/kinematics/b_R')

if __name__ == '__main__':
    vm = CtrlInterface()
    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Shutting down")

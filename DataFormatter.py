import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import math
import collections
import joblib

class DataFromatter():

    def __init__(self) -> None:
        self.subject_masses= {
        "Subject1" : 83.25,
        "Subject2" : 86.48,
        "Subject3" : 87.54,
        "Subject4" : 86.11,
        "Subject5" : 74.91,
        "Subject6" : 111.91,
        "Subject7" : 82.64,
        "Subject8" : 90.44 }

        self.avg_mass = sum(self.subject_masses.values())/len(self.subject_masses)

    # Load data
    def loadData(self, path):
        data = json.load(open(path))
        return data
    
    def flipXZAxes(self, trials):
        for trial in trials:
            grfs = trial.get("grf")
            grfs['ground_force1_vx']=[i * -1 for i in grfs['ground_force1_vx']]
            grfs['ground_force1_vz']=[i * -1 for i in grfs['ground_force1_vz']]
            grfs['ground_force2_vx']=[i * -1 for i in grfs['ground_force2_vx']]
            grfs['ground_force2_vz']=[i * -1 for i in grfs['ground_force2_vz']]
    
    def fixFlippedXZAxes(self, movements):
        self.flipXZAxes(movements["CounterMovementJump"][:3])
        self.flipXZAxes(movements["SingleLegJumpR"][:3])
        self.flipXZAxes(movements["SingleLegJumpL"][:3])
        self.flipXZAxes(movements["SquatJump"][:2])
        self.flipXZAxes(movements["LSingleLegSquat"][:3])
        self.flipXZAxes(movements["RSingleLegSquat"][:3])
        self.flipXZAxes(movements["Squat"][:3])
        return movements

    # Categrises each trial into movement list 
    def formatTrialMovements(self, train_data, flip_xz_flag=False):
        movements = collections.OrderedDict()
        for trial in train_data:
            # Format movements into lists by removing trial numbers and _ as these are not consistent
            movement=''.join([i for i in trial.get("movement") if not i.isdigit() and i !='_'])
            movements.setdefault(movement,[])
            movements.get(movement).append(trial)

        if flip_xz_flag:
            return self.fixFlippedXZAxes(movements)
        else: return movements

    # Returns joined list of trials for specified movement
    def getMovementTrials(self, movement, data):
        movement_data = []
        for type in data:
            if movement.lower() == type.lower() or movement == "all":
                movement_data.extend(data[type])
        
        if len(movement_data)==0:
            print("ERROR: NO DATA WITH MOVEMENT TYPE:",movement)
            exit()

        return movement_data

    # Return dictonary of {x1:[x1,...,xt], y1:[y1,...,yt], z1:[z1,...,zt],
    #                   ..., x17:[x1,...,xt],y17:[y1,...,yt], z17:[z1,...,zt]}
    def getTriangulatedPose(self, trial):
        frames = trial.get("frames")
        max_kps = math.ceil(len(trial.get("grf").get("time"))/12)

        # Create dictionary with empty list for 51 points
        keypoints_data = {}
        for num in range(1,18):
            keypoints_data.setdefault("x"+str(num),[])
            keypoints_data.setdefault("y"+str(num),[])
            keypoints_data.setdefault("z"+str(num),[])

        # Populate point lists with data from each frame in trial
        counter=0
        for idx in range(len(frames)):
            if idx == max_kps: break
            frame = frames[idx]
            pose_kps = frame.get("triangulated_pose")
            for kp_idx in range(len(pose_kps)):
                x,y,z = pose_kps[kp_idx]
                keypoints_data.get("x"+str(kp_idx+1)).append(x)
                keypoints_data.get("y"+str(kp_idx+1)).append(y)
                keypoints_data.get("z"+str(kp_idx+1)).append(z)
            counter+=1
        return keypoints_data

    # Populates pose data so that the number of datapoints matches force data. 
    # Force data captured at 600hz
    # Pose data captured at 50hz
    # Data point gaps are filled by using incremental difference
    def populatePoseGaps(self, pose_data, forces_length):
        num_extra_points = 11

        # Loop through keypoints list
        for kp_label in pose_data:
            kps = pose_data.get(kp_label)
            increased_kps=[]

            #Loop frame postions in list
            for kp_idx in range(len(kps)):
                kp_value = kps[kp_idx]

                # If frame is not last one
                if kp_idx<len(kps)-1:

                    kp_next_value= kps[kp_idx+1]
                    increased_kps.append(kp_value)
                    inc=(kp_next_value-kp_value)/num_extra_points

                    # Add 11 extra points, incrementing difference between frames
                    for _ in range(num_extra_points):
                        kp_value+=inc
                        increased_kps.append(kp_value)
                else:
                    while len(increased_kps)<forces_length:
                        increased_kps.append(kp_value)

            pose_data[kp_label]=increased_kps
        return pose_data
        
    def addAccelerationsToData(self, data, forces, mass, num_frames, linear_interpolation):
        
        for force_label in forces:

            if force_label!="time":

                if linear_interpolation:
                    f_to_add = [f/mass for f in forces[force_label]]
                    if (len(f_to_add)!=num_frames):
                        print("Number of pose frames does not equal number of forces")
                        print("Pose frames length: ",num_frames)
                        print("Forces length: ",len(f_to_add))
                        exit()
                    data[force_label] = f_to_add
                else:
                    avg_accelerations = []
                    for idx in range(0,len(forces[force_label]),12):
                        fs_to_avg = forces[force_label][idx:idx+12]
                        avg_accelerations.append((sum(fs_to_avg)/len(fs_to_avg))/mass)
                        if len(avg_accelerations) == num_frames:
                            break
                    
                    data[force_label] = avg_accelerations

        return data

    # Collects and formats data
    # creates a list of dataframes 
    def collectFormatData(self, train_trials, linear_interpolation=False):
        trial_data = []

        for idx in range(len(train_trials)):
            trial = train_trials[idx]
            forces = trial.get("grf")
            trial_label = "trail_"+str(idx+1)

            data = self.getTriangulatedPose(trial)

            if linear_interpolation:
                data = self.populatePoseGaps(data, len(forces.get("time")))

            num_frames = len(data.get("x1"))
            mass=self.subject_masses.get(trial.get("subject"))

            # Get time to be used as data frame index
            frames = [(trial_label,frame) for frame in range(1,num_frames+1)]
            
            data = self.addAccelerationsToData(data,forces,mass,num_frames,linear_interpolation)
            
            try:
                trial_data.append(pd.DataFrame(data,index=frames).astype(float))
            except Exception as e:
                print("Num of KP frames:",num_frames)
                print("Num of forces:",len(forces.get("time")))
                print("Pose kps length:",len(data.get("x1")))
                print("AVG Force data length:",len(data.get('ground_force1_vx')))
                print(self.dict_dims(data))
                print(e)
                exit()
        return trial_data

    def dict_dims(self, mydict):
        d1 = len(mydict)
        d2 = []
        for d in mydict:
            d2.append((d,len(mydict[d])))
        return d1, d2

    def validateData(self,data):
        return np.isnan(np.sum(data))
    
    def formatDataSamples(self, trial_data, sample_size, end_force=False):
        #Empty lists to be populated using formatted training data
        trainX = []
        trainY = []

        # Reformat input data into a shape: (n_samples x timesteps x n_features)
        # Forming each x and y by sliding window of sample_size data points   
        # Each force predictor is the middle force of key points
        print("FORMATTING DATA TO (n_samples x timesteps x n_features)")
        trial_lengths = []
        counter=0
        for trial in trial_data:
            for idx in range(sample_size, len(trial)):
                counter+=1

                start = idx - sample_size
                end = idx-1
                middle = start+((end-start)/2)

                trainX.append(trial.loc[idx - sample_size: idx-1, 0:50])
                if end_force:
                        trainY.append(trial.loc[idx-1, 51:56])
                else:
                    if middle%2 == 0:
                        trainY.append(trial.loc[middle, 51:56])
                    else:
                        trainY.append(trial.loc[math.floor(middle):math.ceil(middle), 51:56].mean())
            trial_lengths.append(counter)
        trainX, trainY = np.array(trainX), np.array(trainY)

        if self.validateData(trainX) or self.validateData(trainY):
            print("ERROR, NaN DETECTED IN DATA")

        return trainX, trainY, trial_lengths
    
    def loadScaler(self, model_name):
        # Load model & scaler
        return joblib.load("Models/scalers/scaler_"+model_name+".gz")
    
    def inverseNormalize(self, data, model_name):
        scaler = self.loadScaler(model_name)
        return scaler.inverse_transform(data)

    # LSTM uses sigmoid and tanh that are sensitive to magnitude so values need to be normalized
    # normalize the dataset
    def NormaliseData(self, trial_data, model_name):
        try:
            scaler = self.loadScaler(model_name)
        except:
            scaler = StandardScaler()
            scaler = scaler.fit(pd.concat(trial_data))
            # Save scaler
            print("SAVING DATA SCALER")
            joblib.dump(scaler, "Models/scalers/scaler_"+model_name+".gz")

        for idx in range(len(trial_data)):
            trial = trial_data[idx]
            trial_data[idx] = pd.DataFrame(data=scaler.transform(trial))
        return trial_data
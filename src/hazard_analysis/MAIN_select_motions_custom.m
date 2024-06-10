% This code is used to select ground motions with response spectra 
% representative of a target scenario earthquake, as predicted by a ground 
% motion model. Spectra can be selected to be consistent with the full
% distribution of response spectra, or conditional on a spectral amplitude
% at a given period (i.e., using the conditional spectrum approach). 
% Single-component or two-component motions can be selected, and several
% ground motion databases are provided to search in. Further details are
% provided in the following documents:
%
%   Baker, J. W., and Lee, C. (2018). ?An Improved Algorithm for Selecting 
%   Ground Motions to Match a Conditional Spectrum.? Journal of Earthquake 
%   Engineering, 22(4), 708?723.
%
% Version 1.0 created by Nirmal Jayaram, Ting Lin and Jack Baker, Official release 7 June, 2010 
% Version 2.0 created by Cynthia Lee and Jack Baker, last updated, 23 August, 2016
% Updated 6/12/2020 by Jack Baker to include new CyberShake ground motion data
%
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Variable definitions and user inputs
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
% 
%
% selectionParams       : parameters controlling how the ground motion 
%                         selection is performed
%           .databaseFile : filename of the target database. This file should exist 
%                           in the 'Databases' subfolder. Further documentation of 
%                           these databases can be found at 
%                           'Databases/WorkspaceDocumentation***.txt'.
%           .cond       : 0 to run unconditional selection
%                         1 to run conditional
%           .arb        : 1 for single-component selection and arbitrary component sigma
%                         2 for two-component selection and average component sigma
%           .RotD       : 50 to use SaRotD50 data
%                       : 100 to use SaRotD100 data
%           .isScaled   : =1 to allow records to be scaled, =0 otherwise 
%                         (note that the algorithm is slower when .isScaled
%                         = 1)
%           .maxScale   : The maximum allowable scale factor
%           .tol        : Tolerable percent error to skip optimization 
%           .optType    : =0 to use the sum of squared errors to 
%                         optimize the selected spectra, =1 to use 
%                         D-statistic calculations from the KS-test
%                         (the algorithm is slower when .optType
%                         = 1)
%           .penalty    : >0 to penalize selected spectra more than 
%                         3 sigma from the target at any period, 
%                         =0 otherwise.
%           .weights    : [Weights for error in mean, standard deviation 
%                         and skewness] e.g., [1.0,2.0 0.3] 
%           .nLoop      : Number of loops of optimization to perform.
%           .nBig       : The number of spectra that will be searched
%           .indTcond   : Index of Tcond, the conditioning period
%           .recID      : Vector of index values for the selected
%                         spectra
%           .matchV     : =1 to include vertical (V) components of ground
%                         motion in the selection process
%           .TminV      : Shortest vibration period of interest for V
%                         component (applies only when matchV=1)
%           .TmaxV      : Longest vibration period of interest for V
%                         component (applies only when matchV=1)
%           .weightV    : Weight specifying importance of V component
%                         relative to H components (applies only when
%                         matchV=1)
%           .sepScaleV  : =1 to compute separate scale factor for V
%                         components via corresponding target spectrum
%                         (applies only when matchV=1)
% 
% rup                   :  A structure with parameters that specify the rupture scenario
%                          for the purpose of evaluating a GMPE. Here we
%                          use the following parameters
%           .M_bar            : earthquake magnitude
%           .Rjb              : closest distance to surface projection of the fault rupture (km)
%           .Fault_Type       : =0 for unspecified fault
%                               =1 for strike-slip fault
%                               =2 for normal fault
%                               =3 for reverse fault
%           .region           : =0 for global (incl. Taiwan)
%                               =1 for California 
%                               =2 for Japan 
%                               =3 for China or Turkey 
%                               =4 for Italy
%           .z1               : basin depth (km); depth from ground surface to the 1km/s shear-wave horizon, =999 if unknown
%           .Vs30             : average shear wave velocity in the top 30m of the soil (m/s)
%
% targetSa              :  Response spectrum target values to match
%           .meanReq            : Estimated target response spectrum means (vector of
%                                 logarithmic spectral values, one at each period)
%           .covReq             : Matrix of response spectrum covariances
%           .stdevs             : A vector of standard deviations at each period
% 
% IMs                   :  The intensity measure values (from SaKnown) chosen and the 
%                           values available
%           .recID              : indices of selected spectra
%           .scaleFac           : scale factors for selected spectra
%           .sampleSmall        : matrix of selected logarithmic response spectra 
%           .sampleBig          : The matrix of logarithmic spectra that will be 
%                                 searched
%           .stageOneScaleFac   : scale factors for selected spectra, after
%                                 the first stage of selection
%           .stageOneMeans      : mean log response spectra, after
%                                 the first stage of selection
%           .stageOneStdevs     : standard deviation of log response spectra, after
%                                 the first stage of selection
% 
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
% OUTPUT VARIABLES
%
% IMs.recID      : Record numbers of selected records
% IMs.scaleFac   : Corresponding scale factors
%
% (these variables are also output to a text file in write_output.m)
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

addpath('extra/structural_analysis/external_tools/CS_Selection');
addpath('extra/structural_analysis/external_tools/CS_Selection/Databases');

input_filename = 'extra/structural_analysis/results/site_hazard/CS_Selection_input_file.csv';
data = readtable(input_filename);

numRows = size(data, 1);

for row = numRows:-1:1
    Tcond = data{row, 2};
    Mbar = data{row, 3};
    Rjb = data{row, 4};
    eps_bar = data{row, 5};
    Vs30 = data{row, 6};
    outputDir = data{row, 7}{1};
    outputFile = data{row, 8}{1};
    hazard_level = data{row, 10};


    %% User inputs begin here
    % Ground motion database and type of selection 
    selectionParams.databaseFile    = 'NGA_W2_meta_data'; 
    selectionParams.cond            = 1;
    selectionParams.arb             = 2; 
    selectionParams.RotD            = 50;

    % Number of ground motions and spectral periods of interest
    selectionParams.nGM        = 40;  % number of ground motions to be selected 
    selectionParams.Tcond      = Tcond; % Period at which spectra should be scaled and matched 
    selectionParams.Tmin       = 0.1; % smallest spectral period of interest
    selectionParams.Tmax       = 10;  % largest spectral period of interest
    selectionParams.TgtPer = logspace(log10(selectionParams.Tmin),log10(selectionParams.Tmax),30); % compute an array of periods between Tmin and Tmax
    selectionParams.SaTcond    = [];   % (optional) target Sa(Tcond) to use when 
                                       % computing a conditional spectrum 
                                       % if a value is provided here, rup.eps_bar 
                                       % will be back-computed in
                                       % get_target_spectrum.m. If this =[], the
                                       % rup.eps_bar value specified below will
                                       % be used

    % Parameters related to (optional) selection of vertical spectra
    selectionParams.matchV          = 0; % =1 to do selection and scaling while matching a vertical spectrum, =0 to not
    selectionParams.TminV           = 0.01; % smallest vertical spectral period of interest
    selectionParams.TmaxV           = 10;  % largest vertical spectral period of interest
    selectionParams.weightV         = 0.5;  % weight on vertical spectral match versus horizontal
    selectionParams.sepScaleV       = 1;  % =1 to scale vertical components separately from horizontal, =0 to have same scale factor for each
    selectionParams.TgtPerV = logspace(log10(selectionParams.TminV),log10(selectionParams.TmaxV),20); % compute an array of periods between Tmin and Tmax

    % other parameters to scale motions and evaluate selections 
    selectionParams.isScaled   = 1;
    selectionParams.maxScale   = 5.0;
    selectionParams.tol        = 10;
    selectionParams.optType    = 0; 
    selectionParams.penalty    = 0;
    selectionParams.weights    = [1.0 2.0 0.3];
    selectionParams.nLoop      = 10;
    selectionParams.useVar     = 1;   % =1 to use computed variance, =0 to use a target variance of 0

    % User inputs to specify the target earthquake rupture scenario
    rup.M_bar       = Mbar;      % earthquake magnitude
    rup.Rjb         = Rjb;       % closest distance to surface projection of the fault rupture (km)
    rup.eps_bar     = eps_bar;      % epsilon value (used only for conditional selection)
    rup.Vs30        = Vs30;      % average shear wave velocity in the top 30m of the soil (m/s)
    rup.z1          = 999;      % basin depth (km); depth from ground surface to the 1km/s shear-wave horizon,
                                % =999 if unknown
    rup.region      = 1;        % =0 for global (incl. Taiwan)
                                % =1 for California
                                % =2 for Japan
                                % =3 for China or Turkey
                                % =4 for Italy
    rup.Fault_Type  = 1;        % =0 for unspecified fault
                                % =1 for strike-slip fault
                                % =2 for normal fault
                                % =3 for reverse fault

    % Additional seismological parameters as inputs to GMPE by Bozorgnia and Campbell 2016 for V component                        
    rup.Rrup        = Rjb;       % closest distance to rupture plane (km)
    rup.Rx          = Rjb;       % horizontal distance to vertical surface projection of the top edge of rupture plane, measured perpendicular to the strike (km)       
    rup.W           = 15;       % down-dip rupture width (km)  
    rup.Ztor        = 0;        % depth to top of rupture (km)  
    rup.Zbot        = 15;       % depth to bottom of seismogenic crust (km)  
    rup.dip         = 90;       % fault dip angle (deg)  
    rup.lambda      = 0;        % rake angle (deg)  
    rup.Fhw         = 0;        % flag for hanging wall 
    rup.Z2p5        = 1;        % depth to Vs=2.5 km/sec (km)  
    rup.Zhyp        = 10;       % hypocentral depth of earthquake, measured from sea level (km)                              
    rup.FRV         = 0;        % flag for reverse and reverse-oblique faulting
    rup.FNM         = 0;        % flag for normal and normal-oblique faulting
    rup.Sj          = 0;        % flag for regional site effects; =1 for Japan sites and =0 otherwise

    % Ground motion properties to require when selecting from the database. 
    allowedRecs.Vs30 = [-Inf Inf];     % upper and lower bound of allowable Vs30 values 
    allowedRecs.Mag  = [-Inf Inf];     % upper and lower bound of allowable magnitude values
    allowedRecs.D    = [-Inf Inf];     % upper and lower bound of allowable distance values
                                       % allowedRecs.idxInvalid = []; % Index numbers of ground motions to be excluded from consideration for selection 
    allowedRecs.idxInvalid = [1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 22, 23, 24, 25, 26, 27, 28, 30, 31, 33, 34, 36, 37, 40, 41, 42, 45, 50, 51, 52, 56, 57, 65, 68, 70, 71, 77, 78, 79, 88, 92, 94, 95, 96, 97, 99, 103, 106, 108, 109, 112, 121, 122, 123, 125, 126, 127, 128, 130, 131, 132, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 152, 153, 154, 155, 156, 158, 159, 160, 161, 162, 164, 165, 167, 169, 170, 171, 172, 173, 174, 175, 176, 178, 179, 180, 181, 182, 183, 184, 186, 187, 188, 191, 209, 210, 211, 212, 213, 214, 216, 221, 222, 223, 225, 229, 230, 231, 232, 233, 235, 236, 237, 239, 240, 242, 243, 248, 249, 250, 253, 265, 266, 268, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 292, 297, 300, 302, 305, 306, 307, 308, 309, 310, 311, 313, 314, 315, 316, 317, 318, 319, 320, 322, 323, 324, 326, 328, 329, 330, 331, 332, 334, 335, 336, 337, 338, 339, 341, 342, 345, 348, 351, 352, 353, 357, 358, 359, 364, 367, 368, 369, 372, 373, 391, 405, 406, 407, 412, 415, 418, 420, 421, 422, 427, 434, 435, 438, 442, 445, 446, 447, 448, 449, 450, 451, 457, 458, 459, 460, 461, 462, 464, 470, 471, 472, 477, 478, 482, 483, 484, 485, 493, 495, 496, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 514, 516, 517, 521, 522, 527, 529, 530, 534, 540, 543, 544, 545, 547, 548, 549, 550, 551, 554, 558, 564, 565, 566, 568, 569, 570, 571, 572, 573, 574, 576, 577, 578, 579, 580, 582, 583, 584, 585, 587, 589, 590, 592, 595, 600, 602, 611, 612, 614, 615, 616, 619, 621, 626, 630, 638, 639, 645, 647, 652, 690, 692, 700, 718, 719, 720, 721, 722, 723, 724, 725, 726, 727, 728, 729, 730, 731, 732, 733, 734, 735, 736, 737, 738, 739, 741, 744, 745, 746, 747, 748, 749, 751, 752, 753, 754, 755, 756, 757, 758, 759, 760, 761, 762, 763, 764, 765, 766, 767, 768, 771, 772, 776, 777, 778, 779, 780, 781, 783, 784, 785, 786, 787, 788, 791, 793, 794, 795, 796, 799, 800, 801, 802, 803, 804, 806, 808, 810, 811, 814, 815, 816, 817, 818, 819, 820, 821, 822, 825, 826, 827, 828, 832, 833, 835, 836, 838, 841, 844, 847, 848, 849, 850, 853, 855, 856, 861, 862, 864, 868, 874, 879, 881, 882, 885, 888, 889, 890, 891, 895, 896, 900, 901, 902, 906, 907, 910, 916, 918, 930, 931, 937, 942, 943, 944, 945, 946, 947, 948, 949, 952, 953, 954, 956, 958, 959, 960, 962, 963, 964, 970, 971, 974, 975, 978, 982, 983, 985, 986, 987, 988, 989, 993, 995, 996, 998, 999, 1001, 1004, 1005, 1006, 1008, 1012, 1015, 1019, 1022, 1024, 1026, 1031, 1035, 1038, 1039, 1042, 1043, 1044, 1045, 1048, 1049, 1051, 1052, 1054, 1057, 1059, 1063, 1071, 1074, 1077, 1078, 1079, 1083, 1084, 1085, 1086, 1087, 1088, 1089, 1093, 1094, 1099, 1100, 1101, 1102, 1104, 1105, 1106, 1107, 1108, 1109, 1110, 1111, 1113, 1114, 1115, 1116, 1117, 1118, 1119, 1120, 1121, 1122, 1123, 1124, 1126, 1127, 1131, 1135, 1136, 1137, 1139, 1141, 1144, 1145, 1146, 1147, 1148, 1149, 1153, 1155, 1156, 1157, 1158, 1159, 1160, 1161, 1162, 1163, 1164, 1165, 1166, 1176, 1177, 1180, 1181, 1182, 1183, 1184, 1186, 1187, 1188, 1192, 1193, 1194, 1197, 1198, 1199, 1201, 1202, 1203, 1204, 1205, 1206, 1208, 1209, 1210, 1211, 1212, 1213, 1215, 1219, 1220, 1221, 1223, 1224, 1226, 1227, 1229, 1230, 1231, 1232, 1234, 1235, 1236, 1237, 1238, 1243, 1244, 1246, 1247, 1256, 1258, 1259, 1260, 1261, 1262, 1264, 1265, 1268, 1269, 1270, 1271, 1274, 1275, 1276, 1277, 1280, 1281, 1282, 1283, 1286, 1288, 1289, 1290, 1291, 1292, 1293, 1294, 1295, 1296, 1300, 1301, 1302, 1303, 1310, 1312, 1313, 1314, 1315, 1316, 1317, 1318, 1319, 1323, 1324, 1329, 1330, 1331, 1332, 1334, 1336, 1337, 1339, 1346, 1347, 1348, 1350, 1361, 1375, 1380, 1396, 1402, 1410, 1411, 1412, 1413, 1414, 1415, 1417, 1418, 1419, 1421, 1422, 1425, 1427, 1430, 1434, 1436, 1437, 1441, 1445, 1451, 1455, 1456, 1458, 1459, 1460, 1465, 1469, 1471, 1479, 1480, 1482, 1483, 1485, 1487, 1489, 1491, 1492, 1495, 1498, 1500, 1501, 1503, 1504, 1506, 1507, 1508, 1509, 1511, 1512, 1513, 1514, 1515, 1517, 1520, 1521, 1524, 1529, 1533, 1534, 1535, 1536, 1537, 1538, 1540, 1541, 1542, 1545, 1546, 1547, 1549, 1550, 1551, 1553, 1555, 1569, 1572, 1573, 1574, 1581, 1587, 1590, 1599, 1602, 1603, 1605, 1606, 1611, 1612, 1614, 1615, 1617, 1618, 1619, 1622, 1623, 1624, 1626, 1627, 1628, 1629, 1630, 1631, 1632, 1633, 1634, 1636, 1637, 1640, 1641, 1642, 1643, 1644, 1645, 1646, 1740, 1741, 1748, 1749, 1750, 1752, 1754, 1756, 1757, 1759, 1760, 1761, 1762, 1764, 1765, 1766, 1768, 1770, 1776, 1783, 1784, 1785, 1787, 1791, 1792, 1794, 1795, 1805, 1806, 1807, 1810, 1813, 1814, 1816, 1817, 1826, 1829, 1843, 1846, 1847, 1853, 1858, 1866, 1913, 1918, 1927, 1945, 1948, 1990, 1991, 2002, 2003, 2005, 2006, 2007, 2008, 2018, 2019, 2020, 2048, 2050, 2059, 2090, 2095, 2096, 2097, 2099, 2100, 2103, 2104, 2107, 2109, 2110, 2111, 2114, 2121, 2123, 2222, 2402, 2405, 2452, 2454, 2457, 2458, 2459, 2461, 2462, 2463, 2465, 2466, 2467, 2469, 2473, 2475, 2476, 2477, 2478, 2481, 2483, 2487, 2490, 2495, 2498, 2499, 2500, 2501, 2507, 2509, 2540, 2561, 2591, 2600, 2615, 2616, 2618, 2619, 2620, 2623, 2626, 2627, 2628, 2629, 2632, 2635, 2645, 2649, 2650, 2655, 2656, 2661, 2663, 2694, 2695, 2699, 2705, 2707, 2708, 2709, 2711, 2712, 2715, 2718, 2720, 2734, 2739, 2742, 2743, 2746, 2752, 2785, 2796, 2797, 2838, 2853, 2863, 2867, 2873, 2892, 2893, 2900, 2916, 2935, 2937, 2940, 2944, 2947, 2949, 2952, 2954, 2956, 2959, 2965, 2970, 2971, 2973, 2976, 2995, 2997, 3000, 3001, 3004, 3012, 3014, 3017, 3020, 3024, 3025, 3026, 3027, 3029, 3031, 3033, 3040, 3044, 3082, 3095, 3103, 3174, 3178, 3180, 3188, 3201, 3204, 3206, 3207, 3209, 3211, 3213, 3214, 3220, 3221, 3223, 3224, 3225, 3233, 3252, 3256, 3259, 3260, 3262, 3263, 3264, 3265, 3266, 3267, 3268, 3269, 3270, 3271, 3273, 3275, 3276, 3277, 3278, 3281, 3282, 3283, 3286, 3288, 3291, 3292, 3297, 3302, 3303, 3304, 3306, 3307, 3308, 3309, 3311, 3312, 3316, 3317, 3318, 3319, 3320, 3324, 3325, 3327, 3333, 3334, 3340, 3341, 3342, 3353, 3358, 3359, 3362, 3363, 3385, 3404, 3410, 3449, 3458, 3459, 3461, 3463, 3466, 3467, 3472, 3473, 3474, 3475, 3477, 3493, 3495, 3497, 3498, 3503, 3504, 3506, 3507, 3510, 3512, 3515, 3518, 3528, 3529, 3531, 3532, 3533, 3548, 3552, 3553, 3560, 3562, 3564, 3565, 3571, 3584, 3605, 3606, 3634, 3635, 3636, 3639, 3643, 3646, 3652, 3655, 3657, 3661, 3663, 3664, 3665, 3666, 3668, 3670, 3671, 3672, 3673, 3674, 3675, 3676, 3677, 3678, 3679, 3680, 3681, 3682, 3683, 3706, 3713, 3744, 3745, 3746, 3747, 3748, 3749, 3750, 3751, 3752, 3753, 3754, 3756, 3757, 3758, 3760, 3830, 3835, 3844, 3845, 3847, 3849, 3852, 3856, 3857, 3858, 3859, 3861, 3863, 3864, 3865, 3866, 3867, 3870, 3872, 3874, 3879, 3890, 3897, 3907, 3908, 3910, 3914, 3916, 3917, 3933, 3934, 3935, 3938, 3943, 3946, 3947, 3948, 3954, 3959, 3963, 3964, 3965, 3966, 3967, 3968, 3969, 3970, 3974, 3979, 3994, 4013, 4016, 4031, 4037, 4038, 4040, 4045, 4047, 4054, 4059, 4063, 4064, 4065, 4066, 4068, 4070, 4071, 4074, 4078, 4081, 4083, 4084, 4097, 4098, 4099, 4100, 4102, 4104, 4105, 4108, 4111, 4112, 4114, 4115, 4116, 4118, 4122, 4130, 4131, 4132, 4133, 4134, 4135, 4138, 4139, 4142, 4143, 4144, 4145, 4147, 4151, 4152, 4153, 4154, 4155, 4159, 4163, 4169, 4170, 4171, 4184, 4202, 4203, 4204, 4206, 4207, 4208, 4209, 4210, 4211, 4212, 4213, 4214, 4215, 4218, 4219, 4223, 4225, 4227, 4228, 4229, 4230, 4231, 4234, 4239, 4240, 4251, 4252, 4255, 4260, 4261, 4263, 4280, 4281, 4282, 4283, 4284, 4285, 4288, 4291, 4312, 4313, 4314, 4316, 4320, 4328, 4329, 4330, 4331, 4332, 4335, 4336, 4337, 4339, 4345, 4346, 4348, 4349, 4350, 4352, 4390, 4438, 4448, 4451, 4452, 4453, 4454, 4455, 4456, 4457, 4458, 4459, 4460, 4462, 4464, 4472, 4474, 4477, 4478, 4480, 4481, 4482, 4483, 4491, 4515, 4840, 4841, 4842, 4843, 4844, 4845, 4846, 4847, 4848, 4849, 4850, 4852, 4853, 4854, 4855, 4856, 4857, 4858, 4859, 4860, 4861, 4862, 4863, 4864, 4865, 4866, 4868, 4869, 4870, 4872, 4874, 4875, 4876, 4877, 4878, 4879, 4880, 4881, 4882, 4883, 4884, 4886, 4887, 4889, 4890, 4891, 4892, 4894, 4895, 4896, 4983, 4991, 4992, 4997, 5017, 5063, 5068, 5069, 5070, 5089, 5099, 5117, 5178, 5193, 5194, 5220, 5221, 5237, 5238, 5239, 5251, 5253, 5256, 5257, 5259, 5260, 5263, 5264, 5265, 5267, 5270, 5271, 5272, 5283, 5284, 5286, 5291, 5292, 5300, 5341, 5426, 5443, 5448, 5457, 5458, 5464, 5466, 5470, 5471, 5472, 5474, 5475, 5478, 5482, 5483, 5492, 5495, 5536, 5543, 5553, 5598, 5615, 5618, 5619, 5620, 5623, 5629, 5636, 5637, 5647, 5652, 5656, 5657, 5658, 5663, 5664, 5665, 5669, 5672, 5674, 5677, 5678, 5681, 5682, 5698, 5746, 5748, 5751, 5754, 5775, 5777, 5778, 5779, 5780, 5782, 5783, 5784, 5785, 5786, 5788, 5789, 5791, 5794, 5795, 5796, 5798, 5799, 5804, 5806, 5810, 5812, 5813, 5814, 5816, 5817, 5818, 5820, 5821, 5822, 5823, 5824, 5825, 5827, 5829, 5831, 5832, 5835, 5836, 5837, 5847, 5848, 5857, 5865, 5866, 5883, 5906, 5914, 5969, 5971, 5972, 5975, 5985, 5986, 5988, 5989, 5990, 5991, 5992, 6013, 6018, 6059, 6060, 6108, 6147, 6206, 6207, 6208, 6211, 6239, 6242, 6244, 6251, 6340, 6379, 6386, 6584, 6589, 6590, 6592, 6593, 6598, 6614, 6617, 6668, 6711, 6727, 6729, 6731, 6791, 6848, 6857, 6864, 6870, 6874, 6875, 6876, 6877, 6878, 6879, 6882, 6886, 6887, 6888, 6889, 6890, 6891, 6893, 6896, 6897, 6901, 6906, 6911, 6912, 6913, 6915, 6922, 6923, 6927, 6928, 6930, 6948, 6952, 6953, 6959, 6961, 6963, 6966, 6971, 6976, 6980, 6988, 8056, 8057, 8060, 8062, 8063, 8064, 8066, 8067, 8071, 8075, 8083, 8089, 8090, 8099, 8102, 8118, 8119, 8123, 8124, 8127, 8130, 8134, 8136, 8142, 8157, 8158, 8160, 8161, 8164, 8165, 8166, 8167, 8169, 8376, 8407, 8492, 8606, 8617, 8619, 8620, 8621, 8622, 8623, 8625, 8630, 8658, 8674, 8755, 8756, 8759, 8768, 8771, 8776, 8786, 8797, 8836, 8876, 8890, 8897, 8910, 8937, 8973, 8975, 8983, 9003, 9009, 9071, 9130, 9291, 9309, 9319, 9398, 9444, 9447, 9448, 9449, 9457, 9477, 9485, 9493, 9557, 9564, 9567, 9580, 9596, 9654, 9829, 9831, 9838, 9855, 10021, 10100, 10135, 10301, 10414, 10444, 10627, 10736, 10751, 10767, 10809, 10850, 10852, 11035, 11054, 11061, 11062, 11065, 11079, 11085, 11087, 11133, 11252, 11283, 11364, 11606, 11608, 11609, 11620, 11622, 11646, 11647, 11648, 11651, 11653, 11663, 11686, 11699, 11755, 11762, 11772, 11871, 11872, 11984, 12053, 12112, 12157, 12197, 12201, 12204, 12258, 12261, 12263, 12278, 12323, 12371, 12477, 12514, 12561, 12588, 12652, 12806, 12837, 12977, 12991, 13183, 13348, 13702, 13774, 14038, 14113, 14133, 14709, 14923, 14924, 14927, 15176, 15458, 16054, 16404, 17451, 17794, 18006, 18037, 18038, 18069, 18166, 18301, 18383, 18414, 18415, 18421, 18429, 18434, 18443, 18444, 18457, 18472, 18473, 18492, 18494, 18498, 18618, 18756, 18772, 18910, 19043, 19224, 19287, 20125, 20347, 20879, 21409, 21454]; % A list of NGA-West2 records that cannot be retrieved from the PEER website, and so may be preferable to exclude

    % Miscellaneous other inputs
    showPlots   = 0;        % =1 to plot results, =0 to suppress plots
    copyFiles   = 0;        % =1 to copy selected motions to a local directory, 
                            % otherwise =0 to suppress plots
    seedValue   = 1;        % =0 for random seed in when simulating 
                            % response spectra for initial matching, 
                            % otherwise the specifed seedValue is used.
    nTrials     = 50;       % number of iterations of the initial spectral 
                            % simulation step to perform
    % outputDir  = outputDir;    % Location for output files
    % outputFile  = outputFile; % File name of the summary output file

    % User inputs end here
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %% Load the specified ground motion database and screen for suitable motions
    % Load and screen the database
    [SaKnown, selectionParams, indPer, knownPer, metadata] = screen_database(selectionParams, allowedRecs );

    % Save the logarithmic spectral accelerations at target periods
    IMs.sampleBig = log(SaKnown(:,indPer));  
    if selectionParams.matchV == 1
        IMs.sampleBigV = log(selectionParams.SaKnownV(:,selectionParams.indPerV));
    end

    %% Compute target means and covariances of spectral values 
    % Compute target mean and covariance at all periods in the database
    targetSa = get_target_spectrum(knownPer, selectionParams, indPer, rup);

    writematrix(vertcat(selectionParams.TgtPer, targetSa.meanReq)', sprintf('%s/target_mean_%d.csv', outputDir, hazard_level));
    writematrix(vertcat(selectionParams.TgtPer, sqrt(diag(targetSa.covReq))')', sprintf('%s/target_stdv_%d.csv', outputDir, hazard_level));

    % Define the spectral accleration at Tcond that all ground motions will be scaled to
    selectionParams.lnSa1 = targetSa.meanReq(selectionParams.indTcond); 

    %% Simulate response spectra matching the computed targets
    simulatedSpectra = simulate_spectra(targetSa, selectionParams, seedValue, nTrials);

    %% Find best matches to the simulated spectra from ground-motion database
    if selectionParams.matchV == 1
        IMs = find_ground_motionsV( selectionParams, simulatedSpectra, IMs );
    else
        IMs = find_ground_motions( selectionParams, simulatedSpectra, IMs );
    end

    % Store the means and standard deviations of the originally selected ground motions 
    IMs.stageOneScaleFac =  IMs.scaleFac;
    IMs.stageOneMeans = mean(log(SaKnown(IMs.recID,:).*repmat(IMs.stageOneScaleFac,1,size(SaKnown,2))));
    IMs.stageOneStdevs = std(log(SaKnown(IMs.recID,:).*repmat(IMs.stageOneScaleFac,1,size(SaKnown,2))));
    if selectionParams.matchV == 1
        IMs.stageOneScaleFacV =  IMs.scaleFacV;
        IMs.stageOneMeansV = mean(log(selectionParams.SaKnownV(IMs.recID,:).*repmat(IMs.stageOneScaleFacV,1,size(selectionParams.SaKnownV,2))));
        IMs.stageOneStdevsV = std(log(selectionParams.SaKnownV(IMs.recID,:).*repmat(IMs.stageOneScaleFacV,1,size(selectionParams.SaKnownV,2))));
    end

    %% Further optimize the ground motion selection, if needed
    if selectionParams.matchV == 1
        % check errors versus tolerances to see whether optimization is needed
        [ withinTol, IMs ] = within_toleranceV(IMs, targetSa, selectionParams);
        if withinTol == 1
            fprintf('Greedy optimization was skipped based on user input tolerance. \n \n');
            disp(['Median error of ' num2str(IMs.medianErr,2) ' and std dev error of ' num2str(IMs.stdErr,2) ' are within tolerance, skipping optimization']);
        else % run optimization
            IMs = optimize_ground_motionsV(selectionParams, targetSa, IMs);
        end
    else
        % check errors versus tolerances to see whether optimization is needed
        if within_tolerance(IMs.sampleSmall, targetSa, selectionParams)
            fprintf('Greedy optimization was skipped based on user input tolerance. \n \n');
            display(['Error metric of ' num2str(devTotal,2) ' is within tolerance, skipping optimization']);
        else % run optimization
            IMs = optimize_ground_motions(selectionParams, targetSa, IMs);
            % IMs = optimize_ground_motions_par(selectionParams, targetSa, IMs); % a version of the optimization function that uses parallel processing
        end
    end

    %% Plot results, if desired
    if showPlots
        if selectionParams.matchV == 1
            plot_resultsV(selectionParams, targetSa, IMs, simulatedSpectra, SaKnown, knownPer )
        else
            plot_results(selectionParams, targetSa, IMs, simulatedSpectra, SaKnown, knownPer )
        end
    end
    
    %% Output results to a text file 
    recIdx = metadata.allowedIndex(IMs.recID); % selected motions, as indixed in the original database
   
    [path, basename, ext] = fileparts(outputFile);
    write_output(recIdx, IMs, outputDir, basename, metadata)

    %% Copy time series to the working directory, if desired and possible
    if copyFiles
        download_time_series(outputDir, recIdx, metadata)
    end

end

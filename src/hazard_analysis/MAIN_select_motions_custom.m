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
    selectionParams.maxScale   = 3.0;
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
    allowedRecs.idxInvalid = [29 168 177 189 260 267 361 378 365 463 465:467 498 473:475 500 586 588 660 805 829 831 994 1009 1010 1068 1081 1171 1178 1179 1251 1252 1253 1254 1255 1298 1306 1400 1401 1403 1405 1407 1408 1461 1462 1556 1595 1596 1597 1625 1635 4405 4418 4419 4420 4421 4422 4423 4425 4433 4439 4440 4441 4442 4443 4444 4445 4446 4447 4449 4450 4484 4577:4839 6993:8055 9194]; % A list of NGA-West2 records that cannot be retrieved from the PEER website, and so may be preferable to exclude

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

    writematrix(vertcat(selectionParams.TgtPer, targetSa.meanReq)', sprintf('%s/target_mean_%d.csv', outputDir, row));
    writematrix(vertcat(selectionParams.TgtPer, sqrt(diag(targetSa.covReq))')', sprintf('%s/target_stdv_%d.csv', outputDir, row));

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

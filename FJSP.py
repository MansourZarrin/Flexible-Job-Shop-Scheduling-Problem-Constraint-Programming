def create_model(jobs, num_machines, machine_capacities):
    # Creates the CP-SAT model for the flexible job shop problem
    model = cp_model.CpModel()

    # Initialization
    max_job_length = max(len(job) for job in jobs)
    horizon = sum(max(task[0][0] for task in job) for job in jobs)
    starts, presences, job_ends, task_starts = {}, {}, [], []
    intervals_per_resources, demands_per_machine, intervals_per_machine = defaultdict(list), defaultdict(list), defaultdict(list)

    # Creating variables for each job and task
    for job_id, job in enumerate(jobs):
        num_tasks = len(job)
        previous_end = None

        for task_id, task in enumerate(job):
            num_alternatives = len(task)

            # Creating variables for the start, duration, and end of each task
            suffix = f'_j{job_id}_t{task_id}'
            start = model.NewIntVar(0, horizon, 'start' + suffix)
            duration = model.NewIntVar(0, max(max_duration for max_duration, _ in task), 'duration' + suffix)
            end = model.NewIntVar(0, horizon, 'end' + suffix)
            starts[(job_id, task_id)] = start
            task_starts.append(start)
            
            # Adding precedence constraint: each task starts after the previous one ends
            if previous_end is not None:
                model.Add(start >= previous_end)
            previous_end = end

            # Creating alternative intervals and linking them with the main task
            alternative_literals = []
            for alt_id, (alt_duration, machine_id) in enumerate(task):
                alt_suffix = f'_j{job_id}_t{task_id}_a{alt_id}'
                l_presence = model.NewBoolVar('presence' + alt_suffix)
                presences[(job_id, task_id, alt_id)] = l_presence

                l_start = start
                l_duration = alt_duration
                l_end = end
                l_interval = model.NewOptionalIntervalVar(l_start, l_duration, l_end, l_presence, 'interval' + alt_suffix)
                intervals_per_resources[machine_id].append(l_interval)

                # For cumulative constraints
                machine_demand = get_task_demand(job_id, task_id, alt_id)
                demands_per_machine[machine_id].append(machine_demand)
                intervals_per_machine[machine_id].append(l_interval)
                alternative_literals.append(l_presence)

            # Ensure exactly one alternative is chosen for each task
            model.Add(sum(alternative_literals) == 1)

        job_ends.append(previous_end)

    # No overlap constraints for tasks on the same machine
    for machine_id, intervals in intervals_per_resources.items():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)

    # Cumulative constraints for each machine
    for machine_id, intervals in intervals_per_machine.items():
        if len(intervals) > 1:
            demands = demands_per_machine[machine_id]
            capacity = machine_capacities[machine_id]
            model.AddCumulative(intervals, demands, capacity)

    # Objective: minimize the makespan (maximum end time of all jobs)
    makespan = model.NewIntVar(0, horizon, 'makespan')
    model.AddMaxEquality(makespan, job_ends)
    model.Minimize(makespan)
    
    # Initialization for phase information
    max_job_length = max(len(job) for job in jobs)
    phase_min_durations = [cp_model.INT_MAX] * max_job_length
    phase_min_energies = [0] * max_job_length
    phase_machines = [set() for _ in range(max_job_length)]

    # Calculate phase information
    for job in jobs:
        for task_id, task in enumerate(job):
            for alt_id, (alt_duration, machine_id) in enumerate(task):
                phase_min_durations[task_id] = min(phase_min_durations[task_id], alt_duration)
                phase_min_energies[task_id] += alt_duration
                phase_machines[task_id].add(machine_id) 

    # Add energetic lower bound for each phase
    sum_min_durations = sum(phase_min_durations)
    for p in range(max_job_length):
        num_machines_in_phase = len(phase_machines[p])
        min_energetic_duration = phase_min_energies[p] // num_machines_in_phase
        energetic_lower_bound = sum_min_durations - phase_min_durations[p] + min_energetic_duration
        print('Phase', p, ': adding energetic lower bound:', energetic_lower_bound)
        model.Add(makespan >= energetic_lower_bound)

    # Set search heuristic
    model.AddDecisionStrategy(task_starts, cp_model.CHOOSE_LOWEST_MIN, cp_model.SELECT_MIN_VALUE)  

    return model, starts, presences, job_ends

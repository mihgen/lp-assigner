from launchpadlib.launchpad import Launchpad

PROJECTS = ['fuel', 'mos']
STATUS = ['New', 'Confirmed', 'Triaged', 'In Progress', 'Incomplete']
TRUNC = 0
BASE_URL = 'https://api.launchpad.net/devel/'
CREATED_SINCE = '2014-09-01'

# lpbugmanage is the app name. Can be anything
lp = Launchpad.login_with(
    'lpbugmanage', 'production',
    version='devel', credentials_file='credentials.conf',
)

for prj_name in PROJECTS:
    prj = lp.projects[prj_name]
    dev_focus_series = prj.development_focus
    active_milestones = dev_focus_series.active_milestones
    dev_focus_milestone_name = min([m.name for m in active_milestones])
    dev_focus_milestone = prj.getMilestone(name=dev_focus_milestone_name)
    print("Dev focus milestone: %s" % dev_focus_milestone_name)

    older_series = [s for s in prj.series if s.name <= dev_focus_series.name]
    older_milestones_names = []
    for s in older_series:
        milestones = [m.name for m in s.active_milestones]
        if milestones:
            older_milestones_names.append(min(milestones))
    print("Identified milestones for consideration: %s" %
          older_milestones_names)
    #bugs = []
    # Let's iterate over all milestones
    # Unfortunately, LP doesn't allow to search over list of milestones
    bugs = prj.searchTasks(status=STATUS, created_since=CREATED_SINCE)

    print("%s: amount of bugs found - %d" % (prj_name, len(list(bugs))))
    for (counter, bug) in enumerate(bugs, 1):
        bug_mstn = bug.milestone
        print bug, bug_mstn
        # milestone can be None. It can be non-triaged bug
        # Not sure, if other related tasks could have milestone
        series = []
        milestones = []
        if bug_mstn is not None:
            min_milestone_name = bug_mstn.name
            # We don't want to target milestone, which is there
            # even if there is no series associated
            milestones = [bug_mstn.name]
        else:
            min_milestone_name = dev_focus_milestone_name

        for task in bug.related_tasks:
            # We are gethering all series & milestones bug affects
            series.append(task.target.name)
            if task.milestone is None:
                # Apparently affecting only series, no milestone set
                continue
            milestone_name = task.milestone.name
            milestones.append(milestone_name)
            if milestone_name < min_milestone_name:
                # Looking for lowest milestone set, as we don't trust
                # launchpad in sorting of tasks
                min_milestone_name = milestone_name
        if min_milestone_name >= dev_focus_milestone_name:
            # It is whether non-triaged bug,
            #   or has dev_focus/higher milestone only
            print("Skipping this bug: non-triaged or"
                  " has dev_focus/higher milestone only")
            continue

        print("Lowest milestone: %s" % min_milestone_name)
        needed = filter(lambda x: x >= min_milestone_name,
                        older_milestones_names)

        # If we found that bug already targets "-updates", let's target
        # all higher milestones including updates too.
        # If it was only maintenance version, no 'updates' - then no need
        # to touch higher -updates.
        to_target_milestones = []
        if filter(lambda x: "update" in x, milestones):
            to_target_milestones = list(set(needed) - set(milestones))
        # We want to target only bugs from maintenance milestones
        # and maintenance are in format X.Y.Z, so ceraintly more than 3 sym
        elif any(len(x) > 3 for x in milestones):
            all_updates = filter(lambda x: "update" in x,
                                 older_milestones_names)
            to_target_milestones = list(set(needed) - set(milestones) -
                                        set(all_updates))

        if to_target_milestones:
            print("###### %s: targeting to %s" %
                  (bug.bug.id, to_target_milestones))
        for tgt in to_target_milestones:
            milestone = prj.getMilestone(name=tgt)
            series = milestone.series_target
            ################ targeting code ################

        if counter > TRUNC and TRUNC > 0:
            break
        if counter % 10 == 0:
            print("Processed %d bugs..." % counter)

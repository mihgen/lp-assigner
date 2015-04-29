import itertools

from launchpadlib.launchpad import Launchpad


PROJECTS = ['fuel', 'mos']
STATUS = ['New', 'Confirmed', 'Triaged', 'In Progress', 'Incomplete']
TRUNC = 0
BASE_URL = 'https://api.launchpad.net/devel/'
CREATED_SINCE = '2014-09-01'
DEBUG = 0
MAX_CHANGES = -1

def make_changes(prj, milestones_map, bug, to_target_milestones):
    dev_focus_series = prj.development_focus
    prj_name = prj.name
    for tgt in to_target_milestones:
        milestone = prj.getMilestone(name=tgt)
        s_milestone = bug.milestone
        s_status = bug.status
        s_importance = bug.importance
        s_assignee = bug.assignee
        if tgt in milestones_map[dev_focus_series.name]:
            # This is real dirty magic. Needs refactoring.
            # LP, if you try to target dev focus series,
            # will move your bug data over new target. So, if you
            # had no-series bug with 5.1.2, and now targeting
            # 6.1.x, then you'll get moved all 5.1.2 data over.
            # To avoid data loss, we are exchanging data, and not
            # creating series if milestone is from current dev series
            if not DEBUG:
                try:
                    bug.milestone = milestone
                    bug.status = "New"
                    bug.lp_save()
                    series = s_milestone.series_target.name
                    target = BASE_URL + prj_name + '/' + series
                    task_link = bug.bug.addTask(target=target)
                    task_link.milestone = s_milestone
                    task_link.status = s_status
                    task_link.importance = s_importance
                    task_link.assignee = s_assignee
                    task_link.lp_save()
                    continue
                except Exception as e:
                    print('Error: {}'.format(e))

        series = milestone.series_target.name
        target = BASE_URL + prj_name + '/' + series
        # It can raise exception - 400, if series already exists
        if not DEBUG:
            try:
                #TODO: if series already targeted, but not milestone,
                # then we will skip it - as addTask will return an
                # exception: series already exists
                task_link = bug.bug.addTask(target=target)
                # Series already changed at this point of time,
                # lp_save() below is for milestone to change
                milestone_target = BASE_URL + prj_name + \
                    '/+milestone/' + tgt
                task_link.milestone = milestone_target
                task_link.assignee = s_assignee
                task_link.lp_save()
            except Exception as e:
                print('Error: {}'.format(e))

def bug_milestones(bug, dev_focus_milestone_name):
    bug_info = ""
    bug_id = bug.bug.id
    bug_mstn = bug.milestone
    # milestone can be None. It can be non-triaged bug
    # Not sure, if other related tasks could have milestone
    milestones = []

    # Special list for milestones which are inconsistent with series
    ml_to_add = []
    if bug_mstn is not None:
        min_milestone_name = bug_mstn.name
        # We don't want to target milestone, which is there
        # even if there is no series associated
        milestones = [bug_mstn.name]
    else:
        min_milestone_name = dev_focus_milestone_name

    bug_info = "** {} ** TOP bug object, milestone: {}\n".format(
        bug_id, bug_mstn)
    for task in bug.related_tasks:
        bug_info += "**** {} ** affects: {}, milestone: {}\n".format(
            bug_id, task.target.name, task.milestone)
        # We are gethering all milestones bug affects
        # We are not interested in collecting series, as we think
        #  that milestone is our primary key for all work with LP.
        #  For instance, we filter search by milestone.
        if task.milestone is None:
            # Apparently affecting only series, no milestone set
            #TODO: As it seems to be impossible to update existing task,
            # for unknown reason, we may want to lp_delete() and create
            # task from scratch. We need to save assignee, etc. though.
            continue
        milestone_name = task.milestone.name
        milestones.append(milestone_name)
        if milestone_name < min_milestone_name:
            # Looking for lowest milestone set, as we don't trust
            # launchpad in sorting of tasks
            min_milestone_name = milestone_name

        if task.milestone.series_target.name != task.target.name:
            # This is inconsistency which can exist in LP. For instance,
            #  your bug can be assigned to 4.1.2 milestone in 6.0.x series
            #  We want to fix that. All attempts to just update series
            #  for existing bug task failed. So we have to remove bug task
            #  and create it again.
            print("%s: INCONSISTENCY DETECTED: series %s, milestone %s."
                  " Deleting... " % (bug_id,
                                     task.target.name, milestone_name))
            if not DEBUG:
                # TODO: we need to save all status, assignee, etc.,
                #  and reapply it after
                try:
                    task.lp_delete()
                except Exception as e:
                    print('Error: {}'.format(e))
            ml_to_add.append(milestone_name)
    return (bug_info, milestones, ml_to_add, min_milestone_name)

def main():
    # lpbugmanage is the app name. Can be anything
    lp = Launchpad.login_with(
        'lpbugmanage', 'production',
        version='devel', credentials_file='credentials.conf',
    )

    changes = 0
    for prj_name in PROJECTS:
        prj = lp.projects[prj_name]
        dev_focus_series = prj.development_focus
        active_milestones = dev_focus_series.active_milestones
        dev_focus_milestone_name = min([m.name for m in active_milestones])
        dev_focus_milestone = prj.getMilestone(name=dev_focus_milestone_name)
        print("Dev focus milestone: %s" % dev_focus_milestone_name)

        older_series = [s for s in prj.series if s.name <= dev_focus_series.name]
        milestones_map = {}
        milestones_active_map = {}
        for s in older_series:
            milestones_active_map[s.name] = [m.name for m in s.active_milestones]
            milestones_map[s.name] = [m.name for m in s.all_milestones]

        # Let's iterate over all milestones
        # Unfortunately, LP doesn't allow to search over list of milestones
        bugs = prj.searchTasks(status=STATUS, created_since=CREATED_SINCE)
        print("%s: amount of bugs found - %d" % (prj_name, len(list(bugs))))
        for (counter, bug) in enumerate(bugs, 1):
            bug_id = bug.bug.id
            print("Processing bug #%s..." % bug_id)
            bug_info, milestones, ml_to_add, min_milestone_name = \
                    bug_milestones(bug, dev_focus_milestone_name)
            if not ml_to_add:
                if min_milestone_name >= dev_focus_milestone_name:
                    # It is whether non-triaged bug,
                    #   or has dev_focus/higher milestone only
                    print("%s: Skipping this bug: non-triaged or"
                          " has dev_focus/higher milestone only" % bug_id)
                    continue

                if not any(len(x) > 3 for x in milestones):
                    # We don't want to any further processing with this bug:
                    # we want to target only bugs from maintenance milestones
                    # and maintenance are in format X.Y.Z, X.Y-updates,
                    # or X.Y.Z-updates, so certainly more than 3 sym
                    print("%s: This bug is not targeting any maintenance milestone,"
                          " skipping." % bug_id)
                    continue

            print("%s: Lowest milestone: %s" % (bug_id, min_milestone_name))
            # This is real hack, but it does its job:
            #  We need 6.0.x as min for any 6.0, 6.0.1, 6.0-updates, 6.0.1-updates
            min_series_name = min_milestone_name[:3] + '.x'

            # Without -updates for now...
            needed_series_names = filter(
                lambda x: x >= min_series_name,
                [s.name for s in older_series if 'updates' not in s.name])
            # Let's check if we have -updates
            milestones_updates = [x for x in milestones if 'updates' in x]
            if milestones_updates:
                series_with_updates = [prj.getMilestone(name=x).series_target.name
                                       for x in milestones_updates]
                min_series_with_updates = min(series_with_updates)
                needed_series_names += filter(
                    lambda x: x >= min_series_with_updates,
                    [s.name for s in older_series if 'updates' in s.name])

            print("%s: Verifying that bug targets series: %s" %
                  (bug_id, needed_series_names))
            to_target_milestones = []
            for s in needed_series_names:
                if not set(milestones_map[s]) & set(milestones):
                    if s in milestones_active_map and milestones_active_map[s]:
                        to_target_milestones.append(min(milestones_active_map[s]))

            to_target_milestones += ml_to_add
            if to_target_milestones:
                print bug_info
                to_target_milestones.sort()
                print("%s: ###### targeting to %s" %
                      (bug.bug.id, to_target_milestones))
                ############
                changes += 1
                make_changes(prj, milestones_map, bug, to_target_milestones)

            if counter > TRUNC and TRUNC > 0:
                break
            if changes >= MAX_CHANGES and MAX_CHANGES != -1:
                break
            if counter % 10 == 0:
                print("Processed %d bugs..." % counter)

        # Let's process all High, Critical in current dev milestone
        status = STATUS + ['Fix Committed', 'Fix Released']
        bugs1 = prj.searchTasks(status=status, milestone=dev_focus_milestone,
                                importance=["Critical"],
                                tags=["-devops", "-fuel-devops"],
                                tags_combinator="All",
                                created_since=CREATED_SINCE)
        bugs2 = prj.searchTasks(status=STATUS, milestone=dev_focus_milestone,
                                tags=['customer-found'],
                                created_since=CREATED_SINCE)
        # If current is 6.1.x, then previous is 6.0.x - which we want to target
        prev_series_name = older_series[-2].name
        for bug in itertools.chain(bugs1, bugs2):
            bug_info, milestones, ml_to_add, min_milestone_name = \
                    bug_milestones(bug, dev_focus_milestone_name)
            to_target_milestones = ml_to_add
            if not set(milestones_map[prev_series_name]) & set(milestones):
                to_target_milestones.append(min(milestones_active_map[prev_series_name]))

            if to_target_milestones:
                print bug_info
                to_target_milestones.sort()
                print("%s: ###### targeting to %s" %
                      (bug.bug.id, to_target_milestones))
                ############
                changes += 1
                make_changes(prj, milestones_map, bug, to_target_milestones)

            if changes >= MAX_CHANGES and MAX_CHANGES != -1:
                break

        print("Total changes made: %d" % changes)

if __name__ == "__main__":
    main()
